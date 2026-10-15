from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.db.session import SessionLocal
from app.models.game_round import GameRound
from app.models.game_room import GameRoom
from app.models.player import Player
from app.services import gameplay as gameplay_service
from app.services.drawing_state import drawing_state_store
from app.services.websocket_manager import websocket_manager

router = APIRouter(tags=["WebSocket"])
MAX_MESSAGE_LENGTH = 4096
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _load_connection_context(room_code: str, player_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
        if room is None:
            return None
        player = db.scalar(select(Player).where(Player.id == player_id, Player.room_id == room.id))
        if player is None:
            return None
        return {
            "room_code": room.room_code,
            "room_id": room.id,
            "room_status": room.status,
            "player_id": player.id,
            "username": player.username,
        }


def _set_connection_state(room_id: int, player_id: int, connected: bool) -> bool:
    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.id == player_id, Player.room_id == room_id))
        if player is None:
            return False
        player.is_connected = connected
        if not connected:
            player.last_seen_at = datetime.now()
        db.commit()
        return True


def _get_room_presence(room_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        players = db.scalars(select(Player).where(Player.room_id == room_id).order_by(Player.id.asc())).all()
        return [
            {
                "player_id": player.id,
                "username": player.username,
                "is_host": player.is_host,
                "is_connected": player.is_connected,
                "is_ready": player.is_ready,
                "score": player.score,
            }
            for player in players
        ]


def _get_active_turn(room_code: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
        if room is None or room.status != "in_progress":
            return None
        game_round = db.scalar(select(GameRound).where(
            GameRound.room_id == room.id,
            GameRound.round_number == max(room.current_round_number, 1),
        ))
        if game_round is None or game_round.status != "in_progress" or game_round.drawer_player_id is None or gameplay_service.is_round_expired(game_round):
            return None
        return {
            "round_number": game_round.round_number,
            "drawer_player_id": game_round.drawer_player_id,
            "round_status": game_round.status,
            "duration_seconds": game_round.duration_seconds,
        }


def _get_secret_for_drawer(room_code: str, player_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
        if room is None or room.status != "in_progress":
            return None
        game_round = db.scalar(select(GameRound).where(
            GameRound.room_id == room.id,
            GameRound.round_number == max(room.current_round_number, 1),
            GameRound.status == "in_progress",
            GameRound.drawer_player_id == player_id,
        ))
        if game_round is None or not game_round.secret_word or gameplay_service.is_round_expired(game_round):
            return None
        return {
            "room_code": room.room_code,
            "round_number": game_round.round_number,
            "secret_word": game_round.secret_word,
        }


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "payload": {"code": code, "message": message}})


def _valid_coordinate(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _validate_client_message(
    message: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    event_type = message.get("type")
    payload = message.get("payload", {})
    if not isinstance(event_type, str):
        return None, None, "The event 'type' must be a string."
    if not isinstance(payload, dict):
        return None, None, "The event 'payload' must be a JSON object."

    if event_type == "guess_submit":
        guess = payload.get("guess")
        if not isinstance(guess, str) or not guess.strip() or len(guess.strip()) > 255:
            return event_type, None, "guess must be a non-empty string of at most 255 characters."
        return event_type, {"guess": guess.strip()}, None

    if event_type in {"secret_word_request", "canvas_clear", "canvas_sync_request", "ping"}:
        return event_type, {}, None

    if event_type in {"stroke_start", "stroke_point"}:
        if not _valid_coordinate(payload.get("x")) or not _valid_coordinate(payload.get("y")):
            return event_type, None, "x and y must be numbers between 0 and 1 (normalized canvas coordinates)."
        if event_type == "stroke_start":
            stroke_id = payload.get("stroke_id")
            color = payload.get("color", "#222222")
            width = payload.get("width", 4)
            tool = payload.get("tool", "pen")
            if not isinstance(stroke_id, str) or not 1 <= len(stroke_id) <= 64:
                return event_type, None, "stroke_id must be a string containing 1-64 characters."
            if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
                return event_type, None, "color must be a six-digit hex color such as #222222."
            if not isinstance(width, (int, float)) or isinstance(width, bool) or not 1 <= width <= 40:
                return event_type, None, "width must be a number between 1 and 40."
            if tool not in {"pen", "eraser"}:
                return event_type, None, "tool must be 'pen' or 'eraser'."
            return event_type, {
                "stroke_id": stroke_id,
                "x": float(payload["x"]),
                "y": float(payload["y"]),
                "color": color.lower(),
                "width": float(width),
                "tool": tool,
            }, None
        stroke_id = payload.get("stroke_id")
        if not isinstance(stroke_id, str) or not 1 <= len(stroke_id) <= 64:
            return event_type, None, "stroke_id must be a string containing 1-64 characters."
        return event_type, {"stroke_id": stroke_id, "x": float(payload["x"]), "y": float(payload["y"])}, None

    if event_type == "stroke_end":
        stroke_id = payload.get("stroke_id")
        if not isinstance(stroke_id, str) or not 1 <= len(stroke_id) <= 64:
            return event_type, None, "stroke_id must be a string containing 1-64 characters."
        return event_type, {"stroke_id": stroke_id}, None

    return event_type, None, "Unsupported event type."


def _submit_guess_in_database(room_code: str, player_id: int, guess: str) -> dict[str, Any]:
    with SessionLocal() as db:
        return gameplay_service.submit_guess(db, room_code, player_id, guess)


def _get_leaderboard(room_code: str) -> list[dict[str, Any]]:
    from app.models.game_room import GameRoom

    with SessionLocal() as db:
        room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
        if room is None:
            return []
        return gameplay_service.get_leaderboard_data(db, room.id)


@router.websocket("/ws/rooms/{room_code}/players/{player_id}")
async def room_websocket(websocket: WebSocket, room_code: str, player_id: int) -> None:
    await websocket.accept()
    normalized_room_code = room_code.upper()
    context: dict[str, Any] | None = None
    registered = False
    try:
        context = await run_in_threadpool(_load_connection_context, normalized_room_code, player_id)
        if context is None:
            await _send_error(websocket, "ROOM_OR_PLAYER_NOT_FOUND", "The room or player does not exist, or the player is not in this room.")
            await websocket.close(code=4404, reason="Room or player not found")
            return
        if context["room_status"] == "finished":
            await _send_error(websocket, "ROOM_FINISHED", "Cannot connect to a finished game room.")
            await websocket.close(code=4409, reason="Room already finished")
            return

        first_connection = await websocket_manager.connect(normalized_room_code, player_id, websocket)
        registered = True
        if first_connection:
            connected = await run_in_threadpool(_set_connection_state, context["room_id"], player_id, True)
            if not connected:
                await _send_error(websocket, "PLAYER_NOT_FOUND", "The player no longer exists in this room.")
                await websocket.close(code=4404, reason="Player not found")
                return

        await websocket.send_json({
            "type": "connection_established",
            "payload": {
                "room_code": normalized_room_code,
                "player_id": player_id,
                "username": context["username"],
                "room_status": context["room_status"],
            },
        })
        players = await run_in_threadpool(_get_room_presence, context["room_id"])
        await websocket.send_json({"type": "room_presence", "payload": {"room_code": normalized_room_code, "players": players}})

        secret = await run_in_threadpool(_get_secret_for_drawer, normalized_room_code, player_id)
        if secret:
            await websocket.send_json({"type": "secret_word_assigned", "payload": secret})

        if first_connection:
            await websocket_manager.broadcast_to_room(
                normalized_room_code,
                {"type": "player_connected", "payload": {
                    "room_code": normalized_room_code, "player_id": player_id, "username": context["username"]}},
                exclude_player_id=player_id,
            )

        while True:
            raw_message = await websocket.receive_text()
            if len(raw_message) > MAX_MESSAGE_LENGTH:
                await _send_error(websocket, "MESSAGE_TOO_LARGE", f"Messages cannot exceed {MAX_MESSAGE_LENGTH} characters.")
                continue
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await _send_error(websocket, "INVALID_JSON", "Send a valid JSON object.")
                continue
            if not isinstance(message, dict):
                await _send_error(websocket, "INVALID_MESSAGE", "Each message must be a JSON object.")
                continue

            event_type, payload, validation_error = _validate_client_message(message)
            if validation_error:
                await _send_error(websocket, "INVALID_GUESS" if event_type == "guess_submit" else "INVALID_DRAWING_EVENT", validation_error)
                continue

            if event_type == "ping":
                await websocket.send_json({"type": "pong", "payload": {"timestamp": datetime.now().isoformat()}})
                continue

            if event_type == "secret_word_request":
                secret = await run_in_threadpool(_get_secret_for_drawer, normalized_room_code, player_id)
                if secret is None:
                    await _send_error(websocket, "SECRET_WORD_NOT_AVAILABLE", "Only the assigned drawer can request the active secret word.")
                else:
                    await websocket.send_json({"type": "secret_word_assigned", "payload": secret})
                continue

            if event_type == "guess_submit":
                try:
                    result = await run_in_threadpool(
                        _submit_guess_in_database, normalized_room_code, player_id, payload["guess"]
                    )
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, str) else "Guess could not be processed."
                    await _send_error(websocket, f"GUESS_REJECTED_{exc.status_code}", detail)
                    continue

                if result["kind"] == "round_expired":
                    await websocket_manager.broadcast_to_room(
                        normalized_room_code,
                        {"type": "round_finished", "payload": result["round_finished"]},
                    )
                    await _send_error(websocket, "ROUND_TIME_EXPIRED", "The round time has expired.")
                    continue

                if result["kind"] == "correct":
                    await websocket_manager.broadcast_to_room(
                        normalized_room_code,
                        {"type": "correct_guess", "payload": {
                            "room_code": normalized_room_code,
                            "round_number": result["round_number"],
                            "player_id": result["player_id"],
                            "username": result["username"],
                            "points_awarded": result["points_awarded"],
                            "score": result["score"],
                        }},
                    )
                else:
                    await websocket_manager.broadcast_to_room(
                        normalized_room_code,
                        {"type": "guess_received", "payload": {
                            "room_code": normalized_room_code,
                            "round_number": result["round_number"],
                            "player_id": result["player_id"],
                            "username": result["username"],
                            "guess": result["guess"],
                            "is_correct": False,
                        }},
                    )
                await websocket_manager.broadcast_to_room(
                    normalized_room_code,
                    {"type": "leaderboard_updated", "payload": {"room_code": normalized_room_code, "leaderboard": result["leaderboard"]}},
                )
                if result.get("round_finished"):
                    await websocket_manager.broadcast_to_room(
                        normalized_room_code,
                        {"type": "round_finished", "payload": result["round_finished"]},
                    )
                continue

            if event_type == "canvas_sync_request":
                turn = await run_in_threadpool(_get_active_turn, normalized_room_code)
                await websocket.send_json({"type": "canvas_state", "payload": {
                    "room_code": normalized_room_code,
                    "events": await drawing_state_store.snapshot(normalized_room_code),
                    "active_turn": turn,
                }})
                continue

            turn = await run_in_threadpool(_get_active_turn, normalized_room_code)
            if turn is None:
                await _send_error(websocket, "NO_ACTIVE_DRAWING_TURN", "No active drawing turn exists for this room. The host must start a drawing turn first.")
                continue
            if turn["drawer_player_id"] != player_id:
                await _send_error(websocket, "DRAWING_NOT_ALLOWED", "Only the assigned drawer can send drawing events.")
                continue
            if event_type == "canvas_clear":
                await drawing_state_store.clear(normalized_room_code)
                await websocket_manager.broadcast_to_room(normalized_room_code, {
                    "type": "canvas_cleared",
                    "payload": {"room_code": normalized_room_code, "player_id": player_id, "round_number": turn["round_number"]},
                })
                continue

            outgoing_type = {
                "stroke_start": "stroke_started",
                "stroke_point": "stroke_point",
                "stroke_end": "stroke_ended",
            }[event_type]
            outgoing = {
                "type": outgoing_type,
                "payload": {
                    **payload,
                    "room_code": normalized_room_code,
                    "player_id": player_id,
                    "round_number": turn["round_number"],
                    "timestamp": datetime.now().isoformat(),
                },
            }
            await drawing_state_store.append(normalized_room_code, outgoing)
            await websocket_manager.broadcast_to_room(normalized_room_code, outgoing, exclude_player_id=player_id)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await _send_error(websocket, "INTERNAL_ERROR", "The WebSocket connection encountered an internal error.")
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
    finally:
        if registered and context is not None:
            last_connection = await websocket_manager.disconnect(normalized_room_code, player_id, websocket)
            if last_connection:
                try:
                    await run_in_threadpool(_set_connection_state, context["room_id"], player_id, False)
                    await websocket_manager.broadcast_to_room(normalized_room_code, {
                        "type": "player_disconnected",
                        "payload": {"room_code": normalized_room_code, "player_id": player_id, "username": context["username"]},
                    })
                except Exception:
                    pass
