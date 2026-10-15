from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.game_room import GameRoom
from app.models.player import Player
from app.services import gameplay as gameplay_service
from app.services.drawing_state import drawing_state_store
from app.services.websocket_manager import websocket_manager

router = APIRouter(prefix="/api/rooms", tags=["Rounds, Guessing & Scoring"])
DatabaseSession = Annotated[Session, Depends(get_db)]
RoomCode = Annotated[str, Path(min_length=6, max_length=8, pattern=r"^[A-Za-z0-9]+$")]


class RoundFinishRequest(BaseModel):
    host_player_id: int = Field(gt=0)


class NextRoundRequest(BaseModel):
    host_player_id: int = Field(gt=0)
    duration_seconds: int = Field(default=80, ge=15, le=180)


class LeaderboardItem(BaseModel):
    rank: int
    player_id: int
    username: str
    score: int


@router.post("/{room_code}/rounds/finish", summary="Finish the current round")
async def finish_round(
    room_code: RoomCode,
    payload: RoundFinishRequest,
    db: DatabaseSession,
) -> dict:
    result = gameplay_service.finish_current_round(db, room_code, payload.host_player_id)
    await websocket_manager.broadcast_to_room(
        room_code.upper(),
        {"type": "round_finished", "payload": result},
    )
    return result


@router.post("/{room_code}/rounds/next", summary="Advance to the next round")
async def next_round(
    room_code: RoomCode,
    payload: NextRoundRequest,
    db: DatabaseSession,
) -> dict:
    result = gameplay_service.start_next_round(
        db,
        room_code,
        payload.host_player_id,
        payload.duration_seconds,
    )
    secret_word = result.pop("secret_word", None)
    if secret_word is not None:
        drawer_id = result.get("drawer_player_id")
        if drawer_id is not None:
            await websocket_manager.send_to_player(
                room_code.upper(),
                drawer_id,
                {
                    "type": "secret_word_assigned",
                    "payload": {
                        "room_code": room_code.upper(),
                        "round_number": result["round_number"],
                        "secret_word": secret_word,
                    },
                },
            )
        await drawing_state_store.clear(room_code.upper())
        await websocket_manager.broadcast_to_room(
            room_code.upper(),
            {"type": "round_started", "payload": {
                key: value for key, value in result.items()
                if key != "secret_word"
            }},
        )
    return result


@router.get("/{room_code}/leaderboard", response_model=list[LeaderboardItem], summary="Get the room leaderboard")
def leaderboard(room_code: RoomCode, db: DatabaseSession) -> list[dict]:
    room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")
    return gameplay_service.get_leaderboard_data(db, room.id)


@router.get("/{room_code}/rounds/current", summary="Get public state for the current round")
def current_round(room_code: RoomCode, db: DatabaseSession) -> dict:
    room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()))
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    current = gameplay_service.get_current_round(db, room)
    if current is None:
        return {
            "room_code": room.room_code,
            "round_number": room.current_round_number,
            "status": "not_started",
            "drawer_player_id": None,
            "duration_seconds": None,
            "started_at": None,
            "ended_at": None,
        }
    # Intentionally never expose GameRound.secret_word from a public endpoint.
    return {
        "room_code": room.room_code,
        "round_number": current.round_number,
        "status": current.status,
        "drawer_player_id": current.drawer_player_id,
        "duration_seconds": current.duration_seconds,
        "started_at": current.started_at,
        "ended_at": current.ended_at,
    }
