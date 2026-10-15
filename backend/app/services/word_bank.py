from __future__ import annotations

import secrets

# Keep words simple enough to draw. This list is intentionally server-side.
WORD_BANK: tuple[str, ...] = (
    "airplane", "apple", "astronaut", "bicycle", "bridge", "butterfly",
    "camera", "candle", "castle", "cat", "clock", "cloud", "coffee",
    "computer", "crown", "dolphin", "dragon", "elephant", "envelope",
    "flower", "football", "guitar", "hamburger", "helicopter", "island",
    "jellyfish", "kangaroo", "key", "kite", "ladder", "lemon", "lighthouse",
    "lightning", "mountain", "mushroom", "octopus", "pancake", "penguin",
    "piano", "pizza", "pumpkin", "rainbow", "robot", "rocket", "sandwich",
    "shark", "snowman", "spaceship", "spider", "sunflower", "sunglasses",
    "telephone", "telescope", "tiger", "toothbrush", "tornado", "train",
    "treasure", "turtle", "umbrella", "volcano", "waterfall", "watermelon",
    "whale", "windmill", "wizard", "zebra",
)


def choose_secret_word(previous_word: str | None = None) -> str:
    """Choose a word securely, avoiding immediate repetition when possible."""
    candidates = [word for word in WORD_BANK if word != (previous_word or "").casefold()]
    return secrets.choice(candidates or list(WORD_BANK))
