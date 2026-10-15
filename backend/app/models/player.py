from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game_room import GameRoom
    from app.models.game_round import GameRound
    from app.models.guess import Guess


class Player(Base):
    __tablename__ = "players"

    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "username",
            name="uq_players_room_username",
        ),
        CheckConstraint(
            "score >= 0",
            name="ck_players_score_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    room_id: Mapped[int] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    is_host: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    is_ready: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    score: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        nullable=False,
    )

    is_connected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    room: Mapped[GameRoom] = relationship(
        back_populates="players",
    )

    rounds_drawn: Mapped[list[GameRound]] = relationship(
        back_populates="drawer",
        foreign_keys="GameRound.drawer_player_id",
    )

    guesses: Mapped[list[Guess]] = relationship(
        back_populates="player",
    )