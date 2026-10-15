from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import GameRoom, GameRound, Player


from app.schemas.rooms import (
    GameStartRequest,
    GameStateRead,
    PlayerReadyUpdate,
)


def _get_locked_room(db: Session, room_code: str) -> GameRoom:
    room = db.scalar(
        select(GameRoom)
        .where(GameRoom.room_code == room_code.upper())
        .with_for_update()
        .options(selectinload(GameRoom.players))
    )

    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    return room


def update_player_readiness(
    db: Session,
    room_code: str,
    payload: PlayerReadyUpdate,
) -> GameStateRead:
    """Update readiness for a player who belongs to a waiting room."""
    try:
        room = _get_locked_room(db, room_code)

        if room.status != "waiting":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Readiness can only be changed while the room is waiting.",
            )

        player = db.scalar(
            select(Player)
            .where(
                Player.id == payload.player_id,
                Player.room_id == room.id,
            )
            .with_for_update()
        )

        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found in this room.",
            )

        player.is_ready = payload.is_ready
        db.flush()

        player_count = db.scalar(
            select(func.count(Player.id)).where(Player.room_id == room.id)
        ) or 0

        ready_count = db.scalar(
            select(func.count(Player.id)).where(
                Player.room_id == room.id,
                Player.is_ready.is_(True),
            )
        ) or 0

        db.commit()

        return GameStateRead(
            room_code=room.room_code,
            status=room.status,
            current_round_number=room.current_round_number,
            total_rounds=room.total_rounds,
            player_count=player_count,
            ready_count=ready_count,
            message="Player readiness updated.",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def start_game(
    db: Session,
    room_code: str,
    payload: GameStartRequest,
) -> GameStateRead:
    """Start a waiting room after validating its host and players."""
    try:
        room = _get_locked_room(db, room_code)

        if room.status != "waiting":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The game can only be started from the waiting state.",
            )

        host = db.scalar(
            select(Player)
            .where(
                Player.id == payload.player_id,
                Player.room_id == room.id,
                Player.is_host.is_(True),
            )
            .with_for_update()
        )

        if host is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the room host can start the game.",
            )

        players = list(
            db.scalars(
                select(Player)
                .where(Player.room_id == room.id)
                .order_by(Player.id.asc())
                .with_for_update()
            ).all()
        )

        if len(players) < 2:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least two players are required to start a game.",
            )

        unready_players = [
            player.username for player in players if not player.is_ready
        ]

        if unready_players:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All players must be ready before the game can start.",
            )

        room.status = "in_progress"
        room.current_round_number = 1
        db.flush()
        db.commit()

        return GameStateRead(
            room_code=room.room_code,
            status="in_progress",
            current_round_number=1,
            total_rounds=room.total_rounds,
            player_count=len(players),
            ready_count=len(players),
            message="Game started successfully.",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def restart_game(
    db: Session,
    room_code: str,
    player_id: int,
) -> GameStateRead:
    """Reset a finished room for a fresh game while preserving its players and room code.

    This intentionally removes the room's previous rounds and guesses and resets
    player scores. Only the room host may perform this operation.
    """
    try:
        room = _get_locked_room(db, room_code)

        if room.status not in {"finished", "completed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a finished game can be restarted.",
            )

        host = db.scalar(
            select(Player)
            .where(
                Player.id == player_id,
                Player.room_id == room.id,
                Player.is_host.is_(True),
            )
            .with_for_update()
        )

        if host is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the room host can restart the game.",
            )

        players = list(
            db.scalars(
                select(Player)
                .where(Player.room_id == room.id)
                .order_by(Player.id.asc())
                .with_for_update()
            ).all()
        )

        if len(players) < 2:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least two players are required to restart the game.",
            )

        # Deleting each round cascades to its guesses through the ORM relationship
        # and the database foreign-key constraint.
        old_rounds = list(
            db.scalars(
                select(GameRound)
                .where(GameRound.room_id == room.id)
                .with_for_update()
            ).all()
        )
        for game_round in old_rounds:
            db.delete(game_round)

        for player in players:
            player.score = 0
            player.is_ready = False

        room.status = "waiting"
        room.current_round_number = 0

        db.flush()
        db.commit()

        return GameStateRead(
            room_code=room.room_code,
            status="waiting",
            current_round_number=0,
            total_rounds=room.total_rounds,
            player_count=len(players),
            ready_count=0,
            message=(
                "Room restarted. Previous rounds and scores were cleared. "
                "All players must ready up before starting the new game."
            ),
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
