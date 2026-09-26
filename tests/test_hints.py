import random

from server.game_logic.hints import compute_next_hint_slot
from server.models.card import Card


def make_card(year: int) -> Card:
    return Card(
        deezer_id=0,
        title="Song",
        artist="Artist",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


def test_hint_slot_is_incorrect():
    timeline = [make_card(1990), make_card(2000), make_card(2010)]
    slot = compute_next_hint_slot(timeline, year=2005, already_granted=[], rng=random.Random(1))
    assert slot != 2  # slot 2 (between 2000 and 2010) is the correct one


def test_hint_slot_excludes_already_granted():
    timeline = [make_card(1990), make_card(2000), make_card(2010)]
    # Valid slots: 0,1,2,3. Correct is 2. Incorrect: 0,1,3.
    first = compute_next_hint_slot(timeline, year=2005, already_granted=[], rng=random.Random(2))
    second = compute_next_hint_slot(timeline, year=2005, already_granted=[first], rng=random.Random(2))
    assert second != first
    assert second != 2


def test_hint_slot_returns_none_once_exhausted():
    timeline = [make_card(2000)]
    # Only 2 valid slots total (0, 1); at most 1 can be incorrect for a single-card timeline.
    first = compute_next_hint_slot(timeline, year=2005, already_granted=[], rng=random.Random(1))
    assert first is not None
    second = compute_next_hint_slot(timeline, year=2005, already_granted=[first], rng=random.Random(1))
    assert second is None
