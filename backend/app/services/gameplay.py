from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.game_round import GameRound
from app.models.game_room import GameRoom
from app.models.guess import Guess
from app.models.player import Player
from app.services.word_bank import choose_secret_word

DRAWER_BONUS_POINTS = 25


def normalize_guess(value: str) -> str:
    """Normalize case, whitespace, and punctuation for forgiving comparisons."""
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def round_deadline(game_round: GameRound) -> datetime | None:
    if game_round.started_at is None:
        return None
    return game_round.started_at + timedelta(seconds=game_round.duration_seconds)


def is_round_expired(game_round: GameRound, now: datetime | None = None) -> bool:
    deadline = round_deadline(game_round)
    return deadline is not None and (now or datetime.now()) >= deadline


def get_current_round(db: Session, room: GameRoom, lock: bool = False) -> GameRound | None:
    query = select(GameRound).where(
        GameRound.room_id == room.id,
        GameRound.round_number == max(room.current_round_number, 1),
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _finish_round(db: Session, room: GameRoom, game_round: GameRound, now: datetime) -> dict[str, Any]:
    if game_round.status != "finished":
        game_round.status = "finished"
        game_round.ended_at = now
        correct_count = db.scalar(
            select(func.count(distinct(Guess.player_id))).where(
                Guess.round_id == game_round.id,
                Guess.is_correct.is_(True),
            )
        ) or 0
        if correct_count > 0 and game_round.drawer_player_id is not None:
            drawer = db.scalar(
                select(Player).where(Player.id == game_round.drawer_player_id).with_for_update()
            )
            if drawer is not None:
                drawer.score += DRAWER_BONUS_POINTS
        if game_round.round_number >= room.total_rounds:
            room.status = "finished"
    return {
        "room_code": room.room_code,
        "round_number": game_round.round_number,
        "status": "finished",
        "reason": "all_players_guessed" if _all_guessers_solved(db, game_round) else "round_finished",
        "ended_at": game_round.ended_at.isoformat() if game_round.ended_at else now.isoformat(),
    }


def _all_guessers_solved(db: Session, game_round: GameRound) -> bool:
    if game_round.drawer_player_id is None:
        return False
    eligible_ids = set(db.scalars(
        select(Player.id).where(
            Player.room_id == game_round.room_id,
            Player.id != game_round.drawer_player_id,
        )
    ).all())
    if not eligible_ids:
        return False
    solved_ids = set(db.scalars(
        select(Guess.player_id).where(
            Guess.round_id == game_round.id,
            Guess.is_correct.is_(True),
        ).distinct()
    ).all())
    return eligible_ids.issubset(solved_ids)


def submit_guess(db: Session, room_code: str, player_id: int, message: str) -> dict[str, Any]:
    """Persist a guess and atomically award points once per correct player."""
    try:
        room = db.scalar(
            select(GameRoom).where(GameRoom.room_code == room_code.upper()).with_for_update()
        )
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found.")
        if room.status != "in_progress":
            raise HTTPException(status_code=409, detail="The game is not in progress.")

        game_round = get_current_round(db, room, lock=True)
        if game_round is None or game_round.status != "in_progress":
            raise HTTPException(status_code=409, detail="There is no active round.")
        now = datetime.now()
        if is_round_expired(game_round, now):
            finish_payload = _finish_round(db, room, game_round, now)
            db.commit()
            return {"kind": "round_expired", "round_finished": finish_payload}

        player = db.scalar(
            select(Player).where(
                Player.id == player_id,
                Player.room_id == room.id,
            ).with_for_update()
        )
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found in this room.")
        if player.id == game_round.drawer_player_id:
            raise HTTPException(status_code=403, detail="The drawer cannot submit guesses.")
        if not game_round.secret_word:
            raise HTTPException(status_code=409, detail="The secret word has not been assigned.")

        already_correct = db.scalar(
            select(Guess.id).where(
                Guess.round_id == game_round.id,
                Guess.player_id == player.id,
                Guess.is_correct.is_(True),
            ).limit(1)
        )
        if already_correct is not None:
            raise HTTPException(status_code=409, detail="You have already guessed the word correctly.")

        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=422, detail="Guess cannot be empty.")

        correct = normalize_guess(clean_message) == normalize_guess(game_round.secret_word)
        points = 0
        if correct:
            deadline = round_deadline(game_round)
            remaining = max(0.0, (deadline - now).total_seconds()) if deadline else 0.0
            points = max(10, round(100 * remaining / max(1, game_round.duration_seconds)))
        guess = Guess(
            round_id=game_round.id,
            player_id=player.id,
            message=clean_message[:255],
            is_correct=correct,
            points_awarded=points,
        )
        db.add(guess)
        if correct:
            player.score += points
        db.flush()

        result: dict[str, Any] = {
            "kind": "correct" if correct else "incorrect",
            "room_code": room.room_code,
            "round_number": game_round.round_number,
            "player_id": player.id,
            "username": player.username,
            "is_correct": correct,
            "points_awarded": points,
            "score": player.score,
            "guess": None if correct else clean_message,
        }

        round_finished_payload = None
        if correct and _all_guessers_solved(db, game_round):
            round_finished_payload = _finish_round(db, room, game_round, now)
            round_finished_payload["reason"] = "all_players_guessed"
        db.commit()
        result["round_finished"] = round_finished_payload
        result["leaderboard"] = get_leaderboard_data(db, room.id)
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def get_leaderboard_data(db: Session, room_id: int) -> list[dict[str, Any]]:
    players = db.scalars(
        select(Player).where(Player.room_id == room_id).order_by(Player.score.desc(), Player.username.asc(), Player.id.asc())
    ).all()
    return [
        {"rank": index, "player_id": player.id, "username": player.username, "score": player.score}
        for index, player in enumerate(players, start=1)
    ]


def start_next_round(
    db: Session,
    room_code: str,
    host_player_id: int,
    duration_seconds: int = 80,
) -> dict[str, Any]:
    """Finish an expired round if needed, then create the next round and rotate drawer."""
    try:
        room = db.scalar(
            select(GameRoom).where(GameRoom.room_code == room_code.upper()).with_for_update()
        )
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found.")
        host = db.scalar(select(Player).where(
            Player.id == host_player_id, Player.room_id == room.id, Player.is_host.is_(True)
        ))
        if host is None:
            raise HTTPException(status_code=403, detail="Only the room host can advance rounds.")
        if room.status != "in_progress":
            raise HTTPException(status_code=409, detail="The game is not in progress.")
        current = get_current_round(db, room, lock=True)
        now = datetime.now()
        if current is None:
            raise HTTPException(status_code=409, detail="No current round exists. Start the first drawing turn first.")
        if current.status != "finished":
            if not is_round_expired(current, now):
                raise HTTPException(status_code=409, detail="The current round must finish or expire before advancing.")
            _finish_round(db, room, current, now)
            db.flush()
            if room.status == "finished":
                db.commit()
                return {"room_code": room.room_code, "status": room.status, "message": "All rounds are complete."}

        next_number = current.round_number + 1
        if next_number > room.total_rounds:
            room.status = "finished"
            db.commit()
            return {"room_code": room.room_code, "status": room.status, "message": "All rounds are complete."}

        players = list(db.scalars(
            select(Player).where(Player.room_id == room.id).order_by(Player.id.asc())
        ).all())
        if len(players) < 2:
            raise HTTPException(status_code=409, detail="At least two players are required.")
        player_ids = [player.id for player in players]
        try:
            previous_index = player_ids.index(current.drawer_player_id) if current.drawer_player_id is not None else -1
        except ValueError:
            previous_index = -1
        next_drawer = players[(previous_index + 1) % len(players)]
        game_round = GameRound(
            room_id=room.id,
            round_number=next_number,
            drawer_player_id=next_drawer.id,
            secret_word=choose_secret_word(current.secret_word),
            status="in_progress",
            started_at=now,
            duration_seconds=duration_seconds,
        )
        room.current_round_number = next_number
        db.add(game_round)
        db.flush()
        db.commit()
        return {
            "room_code": room.room_code,
            "round_number": game_round.round_number,
            "drawer_player_id": game_round.drawer_player_id,
            "status": game_round.status,
            "duration_seconds": game_round.duration_seconds,
            "started_at": game_round.started_at.isoformat() if game_round.started_at else None,
            "message": "Next round started. The secret word is sent privately to the drawer.",
            "secret_word": game_round.secret_word,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def finish_current_round(db: Session, room_code: str, host_player_id: int) -> dict[str, Any]:
    try:
        room = db.scalar(select(GameRoom).where(GameRoom.room_code == room_code.upper()).with_for_update())
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found.")
        host = db.scalar(select(Player).where(
            Player.id == host_player_id, Player.room_id == room.id, Player.is_host.is_(True)
        ))
        if host is None:
            raise HTTPException(status_code=403, detail="Only the room host can finish a round.")
        current = get_current_round(db, room, lock=True)
        if current is None or current.status != "in_progress":
            raise HTTPException(status_code=409, detail="There is no active round to finish.")
        payload = _finish_round(db, room, current, datetime.now())
        db.commit()
        payload["room_status"] = room.status
        payload["leaderboard"] = get_leaderboard_data(db, room.id)
        return payload
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
