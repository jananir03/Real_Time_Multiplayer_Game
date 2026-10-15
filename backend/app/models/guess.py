from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game_round import GameRound
    from app.models.player import Player


class Guess(Base):
    __tablename__ = "guesses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    round_id: Mapped[int] = mapped_column(
        ForeignKey("game_rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    points_awarded: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    game_round: Mapped[GameRound] = relationship(back_populates="guesses")
    player: Mapped[Player] = relationship(back_populates="guesses")