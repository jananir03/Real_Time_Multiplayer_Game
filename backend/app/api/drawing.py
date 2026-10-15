from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.game_round import GameRound
from app.models.game_room import GameRoom
from app.models.player import Player
from app.services.gameplay import is_round_expired
from app.services.word_bank import choose_secret_word
from app.services.websocket_manager import websocket_manager

router = APIRouter(prefix="/api/rooms", tags=["Drawing Engine"])
DatabaseSession = Annotated[Session, Depends(get_db)]


class DrawingTurnStart(BaseModel):
    """The host assigns the drawer; the word is selected by the server."""
    host_player_id: int = Field(gt=0)
    drawer_player_id: int = Field(gt=0)
    duration_seconds: int = Field(default=80, ge=15, le=180)


class DrawingTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    room_code: str
    round_number: int
    drawer_player_id: int
    status: str
    duration_seconds: int
    started_at: datetime | None
    message: str


@router.post(
    "/{room_code}/drawing/turn",
    response_model=DrawingTurnRead,
    status_code=status.HTTP_200_OK,
    summary="Start or configure the drawing turn",
    description=(
        "The room host assigns the drawer for the current round. The server selects "
        "a secret word and sends it privately to the assigned drawer over WebSocket."
    ),
)
async def start_drawing_turn(
    room_code: Annotated[str, Path(min_length=6, max_length=8, pattern=r"^[A-Za-z0-9]+$")],
    payload: DrawingTurnStart,
    db: DatabaseSession,
) -> DrawingTurnRead:
    try:
        room = db.scalar(
            select(GameRoom).where(GameRoom.room_code == room_code.upper()).with_for_update()
        )
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found.")
        if room.status != "in_progress":
            raise HTTPException(status_code=409, detail="The game must be in progress before a drawing turn can start.")

        host = db.scalar(select(Player).where(
            Player.id == payload.host_player_id,
            Player.room_id == room.id,
            Player.is_host.is_(True),
        ))
        if host is None:
            raise HTTPException(status_code=403, detail="Only the room host can configure the drawing turn.")

        drawer = db.scalar(select(Player).where(
            Player.id == payload.drawer_player_id,
            Player.room_id == room.id,
        ))
        if drawer is None:
            raise HTTPException(status_code=404, detail="Drawer player was not found in this room.")

        round_number = max(room.current_round_number, 1)
        game_round = db.scalar(select(GameRound).where(
            GameRound.room_id == room.id,
            GameRound.round_number == round_number,
        ).with_for_update())
        now = datetime.now()
        changed_drawer = game_round is not None and game_round.drawer_player_id != drawer.id
        expired_round = game_round is not None and is_round_expired(game_round, now)
        if game_round is None:
            game_round = GameRound(
                room_id=room.id,
                round_number=round_number,
                drawer_player_id=drawer.id,
                secret_word=choose_secret_word(),
                status="in_progress",
                started_at=now,
                duration_seconds=payload.duration_seconds,
            )
            db.add(game_round)
        else:
            if game_round.status == "finished":
                raise HTTPException(status_code=409, detail="This round has already finished.")
            game_round.drawer_player_id = drawer.id
            if changed_drawer or expired_round:
                game_round.secret_word = choose_secret_word(game_round.secret_word)
                game_round.started_at = now
                game_round.ended_at = None
            elif not game_round.secret_word:
                game_round.secret_word = choose_secret_word()
            game_round.status = "in_progress"
            game_round.started_at = game_round.started_at or now
            game_round.ended_at = None
            game_round.duration_seconds = payload.duration_seconds

        db.commit()
        db.refresh(game_round)
        secret_word = game_round.secret_word
        response = DrawingTurnRead(
            room_code=room.room_code,
            round_number=game_round.round_number,
            drawer_player_id=drawer.id,
            status=game_round.status,
            duration_seconds=game_round.duration_seconds,
            started_at=game_round.started_at,
            message="Drawing turn is active. The secret word has been selected and sent only to the drawer.",
        )
        # The secret word is deliberately excluded from the HTTP response.
        if secret_word:
            await websocket_manager.send_to_player(
                room.room_code,
                drawer.id,
                {
                    "type": "secret_word_assigned",
                    "payload": {
                        "room_code": room.room_code,
                        "round_number": game_round.round_number,
                        "secret_word": secret_word,
                    },
                },
            )
        await websocket_manager.broadcast_to_room(
            room.room_code,
            {"type": "drawing_turn_started", "payload": {
                "room_code": room.room_code,
                "round_number": game_round.round_number,
                "drawer_player_id": drawer.id,
                "duration_seconds": game_round.duration_seconds,
                "started_at": game_round.started_at.isoformat() if game_round.started_at else None,
            }},
        )
        return response
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
