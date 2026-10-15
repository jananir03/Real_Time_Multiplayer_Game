from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game_round import GameRound
    from app.models.player import Player


class GameRoom(Base):
    __tablename__ = "game_rooms"
    __table_args__ = (
        CheckConstraint(
            "max_players >= 2 AND max_players <= 12",
            name="ck_game_rooms_player_limit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_code: Mapped[str] = mapped_column(
        String(8), unique=True, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="waiting", server_default="waiting", nullable=False
    )
    max_players: Mapped[int] = mapped_column(default=8, server_default="8", nullable=False)
    total_rounds: Mapped[int] = mapped_column(default=3, server_default="3", nullable=False)
    current_round_number: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    players: Mapped[list[Player]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    rounds: Mapped[list[GameRound]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )