import random

import pytest

from server.config import SOLO_MAIN_QUEUE_SIZE
from server.game_logic.daily import MIN_DAILY_DECK_SIZE, daily_order, split_daily_deck
from server.models.card import Card


def make_cards(n: int) -> list[Card]:
    return [
        Card(deezer_id=1000 + i, title=f"t{i}", artist=f"a{i}", release_year=1960 + i, preview_url="p", album_art_url="a")
        for i in range(n)
    ]


def ids(cards: list[Card]) -> list[int]:
    return [c.deezer_id for c in cards]


def test_same_date_and_theme_gives_same_order():
    cards = make_cards(40)
    assert ids(daily_order(cards, "2026-10-04", "general")) == ids(daily_order(cards, "2026-10-04", "general"))


def test_different_dates_give_different_orders():
    cards = make_cards(40)
    assert ids(daily_order(cards, "2026-10-04", "general")) != ids(daily_order(cards, "2026-10-05", "general"))


def test_different_themes_give_different_orders():
    cards = make_cards(40)
    assert ids(daily_order(cards, "2026-10-04", "general")) != ids(daily_order(cards, "2026-10-04", "rock"))


def test_order_does_not_depend_on_input_order():
    cards = make_cards(40)
    shuffled = cards[:]
    random.Random(7).shuffle(shuffled)
    assert ids(daily_order(cards, "2026-10-04", "general")) == ids(daily_order(shuffled, "2026-10-04", "general"))


def test_does_not_mutate_input():
    cards = make_cards(40)
    before = ids(cards)
    daily_order(cards, "2026-10-04", "general")
    assert ids(cards) == before


def test_order_is_a_permutation():
    cards = make_cards(40)
    assert sorted(ids(daily_order(cards, "x", "general"))) == sorted(ids(cards))


def test_split_layout():
    ordered = daily_order(make_cards(40), "2026-10-04", "general")
    split = split_daily_deck(ordered)
    assert split.start is ordered[0]
    assert split.queue == ordered[1 : 1 + SOLO_MAIN_QUEUE_SIZE]
    assert len(split.queue) == SOLO_MAIN_QUEUE_SIZE
    assert split.reserve == ordered[1 + SOLO_MAIN_QUEUE_SIZE :]


def test_split_accepts_minimum_deck():
    assert len(split_daily_deck(make_cards(MIN_DAILY_DECK_SIZE)).reserve) >= 1


def test_split_refuses_too_small_deck():
    with pytest.raises(ValueError, match="needs at least"):
        split_daily_deck(make_cards(MIN_DAILY_DECK_SIZE - 1))
