from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rooms import (
    CloseRoomRequest,
    LeaveRoomRequest,
    PlayerJoin,
    RoomCreate,
    RoomListItem,
    RoomMembership,
    RoomRead,
)
from app.services.rooms import (
    close_room,
    create_room,
    get_room,
    join_room,
    leave_room,
    list_waiting_rooms,
)


router = APIRouter(prefix="/api/rooms", tags=["Game Rooms"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=RoomMembership, status_code=status.HTTP_201_CREATED)
def create_game_room(payload: RoomCreate, db: DatabaseSession) -> RoomMembership:
    return create_room(db, payload)


@router.get("", response_model=list[RoomListItem])
def get_waiting_rooms(
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[RoomListItem]:
    return list_waiting_rooms(db, limit)


@router.get("/{room_code}", response_model=RoomRead)
def get_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    db: DatabaseSession,
) -> RoomRead:
    return get_room(db, room_code)


@router.post(
    "/{room_code}/join",
    response_model=RoomMembership,
    status_code=status.HTTP_200_OK,
)
def join_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: PlayerJoin,
    db: DatabaseSession,
) -> RoomMembership:
    return join_room(db, room_code, payload)


@router.post("/{room_code}/leave", status_code=status.HTTP_200_OK)
def leave_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: LeaveRoomRequest,
    db: DatabaseSession,
) -> dict[str, str]:
    return leave_room(db, room_code, payload)


@router.delete("/{room_code}", status_code=status.HTTP_200_OK)
def delete_game_room(
    room_code: Annotated[str, Path(min_length=6, max_length=8)],
    payload: CloseRoomRequest,
    db: DatabaseSession,
) -> dict[str, str]:
    return close_room(db, room_code, payload)