"""Deterministic deck ordering for the solo daily challenge.

Pure functions only — no networking/asyncio, no `random` module, and no
built-in `hash()` (which is salted per process). Every player on the same
UTC date gets the same songs in the same order because the order is a pure
function of (seed_key, theme, track id).

`seed_key` is the UTC date ("YYYY-MM-DD") the solo session was created on.
"""

import hashlib
from dataclasses import dataclass

from server.config import SOLO_MAIN_QUEUE_SIZE, SOLO_MIN_RESERVE_CARDS
from server.models.card import Card

# start card + main queue + the smallest allowed reserve pool.
MIN_DAILY_DECK_SIZE = 1 + SOLO_MAIN_QUEUE_SIZE + SOLO_MIN_RESERVE_CARDS


@dataclass(frozen=True)
class DailySplit:
    start: Card
    queue: list[Card]
    reserve: list[Card]


def _sort_key(card: Card, seed_key: str, theme: str) -> str:
    return hashlib.sha256(f"{seed_key}:{theme}:{card.deezer_id}".encode()).hexdigest()


def daily_order(cards: list[Card], seed_key: str, theme: str) -> list[Card]:
    """`cards` sorted by sha256 of "{seed_key}:{theme}:{track_id}".

    Independent of the input order (the key depends only on the card's own
    id), and returns a new list rather than mutating `cards`.
    """
    return sorted(cards, key=lambda card: _sort_key(card, seed_key, theme))


def split_daily_deck(ordered: list[Card]) -> DailySplit:
    """Index 0 is the starting card, 1..SOLO_MAIN_QUEUE_SIZE the main queue,
    the rest the reserve pool (consumed in order by switch-track).

    Raises ValueError if the deck is too small to leave at least
    SOLO_MIN_RESERVE_CARDS in reserve.
    """
    if len(ordered) < MIN_DAILY_DECK_SIZE:
        raise ValueError(
            f"deck has {len(ordered)} cards; a solo run needs at least {MIN_DAILY_DECK_SIZE} "
            f"(1 start + {SOLO_MAIN_QUEUE_SIZE} queue + {SOLO_MIN_RESERVE_CARDS} reserve)"
        )
    queue_end = 1 + SOLO_MAIN_QUEUE_SIZE
    return DailySplit(start=ordered[0], queue=ordered[1:queue_end], reserve=ordered[queue_end:])
