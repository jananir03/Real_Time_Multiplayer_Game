from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game_room import GameRoom
    from app.models.guess import Guess
    from app.models.player import Player


class GameRound(Base):
    __tablename__ = "game_rounds"
    __table_args__ = (
        UniqueConstraint(
            "room_id", "round_number", name="uq_game_rounds_room_round_number"
        ),
        CheckConstraint("round_number >= 1", name="ck_game_rounds_number_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    drawer_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Never include this field in public API response schemas.
    secret_word: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(
        default=80, server_default="80", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    room: Mapped[GameRoom] = relationship(back_populates="rounds")
    drawer: Mapped[Player | None] = relationship(
        back_populates="rounds_drawn",
        foreign_keys=[drawer_player_id],
    )
    guesses: Mapped[list[Guess]] = relationship(
        back_populates="game_round",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )