import secrets
import string

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.game_room import GameRoom
from app.models.player import Player
from app.schemas.rooms import (
    CloseRoomRequest,
    LeaveRoomRequest,
    PlayerJoin,
    RoomCreate,
    RoomListItem,
    RoomMembership,
    RoomRead,
)


ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits
ROOM_CODE_LENGTH = 6


def _generate_room_code() -> str:
    return "".join(
        secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH)
    )


def _get_room_or_404(
    db: Session,
    room_code: str,
    *,
    lock: bool = False,
) -> GameRoom:
    statement = (
        select(GameRoom)
        .where(GameRoom.room_code == room_code.upper())
        .options(selectinload(GameRoom.players))
    )

    if lock:
        statement = statement.with_for_update()

    room = db.scalar(statement)

    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    return room


def _room_read(room: GameRoom) -> RoomRead:
    return RoomRead.model_validate(room)


def _membership(room: GameRoom, player: Player) -> RoomMembership:
    return RoomMembership(
        room=_room_read(room),
        player=player,
    )


def create_room(db: Session, payload: RoomCreate) -> RoomMembership:
    """Create a room and its host in one database transaction."""
    try:
        for _ in range(5):
            room_code = _generate_room_code()

            existing_id = db.scalar(
                select(GameRoom.id).where(GameRoom.room_code == room_code)
            )
            if existing_id is not None:
                continue

            room = GameRoom(
                room_code=room_code,
                status="waiting",
                max_players=payload.max_players,
                total_rounds=payload.total_rounds,
                current_round_number=0,
            )
            db.add(room)
            db.flush()

            host = Player(
                room_id=room.id,
                username=payload.username,
                is_host=True,
                score=0,
                is_connected=False,
            )
            db.add(host)
            db.flush()
            db.commit()

            room = _get_room_or_404(db, room_code)
            host = db.scalar(
                select(Player).where(
                    Player.room_id == room.id,
                    Player.id == host.id,
                )
            )
            if host is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Room was created, but its host could not be loaded.",
                )

            return _membership(room, host)

        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not generate a unique room code. Please retry.",
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The room or username conflicts with an existing record. Please retry.",
        ) from exc
    except Exception:
        db.rollback()
        raise


def list_waiting_rooms(db: Session, limit: int = 50) -> list[RoomListItem]:
    """Return recently created waiting rooms with their current player counts."""
    player_counts = (
        select(
            Player.room_id.label("room_id"),
            func.count(Player.id).label("player_count"),
        )
        .group_by(Player.room_id)
        .subquery()
    )

    statement = (
        select(
            GameRoom.id,
            GameRoom.room_code,
            GameRoom.status,
            GameRoom.max_players,
            GameRoom.total_rounds,
            func.coalesce(player_counts.c.player_count, 0).label("player_count"),
            GameRoom.created_at,
        )
        .outerjoin(player_counts, player_counts.c.room_id == GameRoom.id)
        .where(GameRoom.status == "waiting")
        .order_by(GameRoom.created_at.desc())
        .limit(limit)
    )

    rows = db.execute(statement).all()
    return [
        RoomListItem(
            id=row.id,
            room_code=row.room_code,
            status=row.status,
            max_players=row.max_players,
            total_rounds=row.total_rounds,
            player_count=row.player_count,
            created_at=row.created_at,
        )
        for row in rows
    ]


def get_room(db: Session, room_code: str) -> RoomRead:
    room = _get_room_or_404(db, room_code)
    return _room_read(room)


def join_room(
    db: Session,
    room_code: str,
    payload: PlayerJoin,
) -> RoomMembership:
    """Join a waiting room, checking capacity and username uniqueness."""
    try:
        room = _get_room_or_404(db, room_code, lock=True)

        if room.status != "waiting":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This room is not accepting new players.",
            )

        current_count = db.scalar(
            select(func.count(Player.id)).where(Player.room_id == room.id)
        ) or 0

        if current_count >= room.max_players:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This room is full.",
            )

        existing_player = db.scalar(
            select(Player.id).where(
                Player.room_id == room.id,
                func.lower(Player.username) == payload.username.lower(),
            )
        )

        if existing_player is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That username is already taken in this room.",
            )

        player = Player(
            room_id=room.id,
            username=payload.username,
            is_host=False,
            score=0,
            is_connected=False,
        )
        db.add(player)
        db.flush()
        player_id = player.id
        db.commit()

        room = _get_room_or_404(db, room_code)
        player = db.get(Player, player_id)

        if player is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Player joined, but could not be loaded.",
            )

        return _membership(room, player)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The username conflicts with an existing record.",
        ) from exc
    except Exception:
        db.rollback()
        raise


def leave_room(
    db: Session,
    room_code: str,
    payload: LeaveRoomRequest,
) -> dict[str, str]:
    """Remove a player and promote another player if the host leaves."""
    try:
        room = _get_room_or_404(db, room_code, lock=True)

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

        was_host = player.is_host
        db.delete(player)
        db.flush()

        remaining_players = list(
            db.scalars(
                select(Player)
                .where(Player.room_id == room.id)
                .order_by(Player.joined_at.asc(), Player.id.asc())
                .with_for_update()
            ).all()
        )

        if not remaining_players:
            db.delete(room)
            db.commit()
            return {"message": "Player left. The empty room was deleted."}

        if was_host:
            remaining_players[0].is_host = True

        db.commit()
        return {"message": "Player left the room successfully."}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def close_room(
    db: Session,
    room_code: str,
    payload: CloseRoomRequest,
) -> dict[str, str]:
    """Allow the host to close a room."""
    try:
        room = _get_room_or_404(db, room_code, lock=True)

        player = db.scalar(
            select(Player).where(
                Player.id == payload.player_id,
                Player.room_id == room.id,
            )
        )

        if player is None or not player.is_host:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the room host can close this room.",
            )

        if room.status == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active game cannot be closed through this endpoint.",
            )

        db.delete(room)
        db.commit()
        return {"message": "Room closed successfully."}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
