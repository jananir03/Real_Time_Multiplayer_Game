
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoomCreate(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    max_players: int = Field(default=8, ge=2, le=12)
    total_rounds: int = Field(default=3, ge=1, le=10)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,30}", value):
            raise ValueError(
                "Username must contain 2-30 letters, numbers, underscores or hyphens."
            )
        return value


class PlayerJoin(BaseModel):
    username: str = Field(min_length=2, max_length=30)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,30}", value):
            raise ValueError(
                "Username must contain 2-30 letters, numbers, underscores or hyphens."
            )
        return value


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_host: bool
    is_ready: bool
    score: int
    is_connected: bool
    joined_at: datetime


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_code: str
    status: Literal["waiting", "in_progress", "finished"]
    max_players: int
    total_rounds: int
    current_round_number: int
    created_at: datetime
    updated_at: datetime
    players: list[PlayerRead] = Field(default_factory=list)


class RoomMembership(BaseModel):
    room: RoomRead
    player: PlayerRead


class RoomListItem(BaseModel):
    id: int
    room_code: str
    status: Literal["waiting", "in_progress", "finished"]
    max_players: int
    total_rounds: int
    player_count: int
    created_at: datetime


class LeaveRoomRequest(BaseModel):
    player_id: int = Field(gt=0)


class CloseRoomRequest(BaseModel):
    player_id: int = Field(gt=0)


class PlayerReadyUpdate(BaseModel):
    player_id: int = Field(gt=0)
    is_ready: bool


class GameStartRequest(BaseModel):
    player_id: int = Field(gt=0)


class GameStateRead(BaseModel):
    room_code: str
    status: Literal["waiting", "in_progress", "finished"]
    current_round_number: int
    total_rounds: int
    player_count: int
    ready_count: int
    message: str
