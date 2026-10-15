from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rooms import GameStartRequest, GameStateRead, PlayerReadyUpdate
from app.services.game_state import restart_game, start_game, update_player_readiness


router = APIRouter(prefix="/api/rooms", tags=["Game State"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.patch("/{room_code}/ready", response_model=GameStateRead)
def set_player_ready(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: PlayerReadyUpdate,
    db: DatabaseSession,
) -> GameStateRead:
    return update_player_readiness(db, room_code, payload)


@router.post("/{room_code}/start", response_model=GameStateRead)
def start_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: GameStartRequest,
    db: DatabaseSession,
) -> GameStateRead:
    return start_game(db, room_code, payload)


@router.post("/{room_code}/restart", response_model=GameStateRead)
def restart_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: GameStartRequest,
    db: DatabaseSession,
) -> GameStateRead:
    """Restart a finished room as a fresh game, preserving its room and players."""
    return restart_game(db, room_code, payload.player_id)
