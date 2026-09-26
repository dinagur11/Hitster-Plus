from server.game_logic.placement import is_placement_correct, valid_slot_indices
from server.models.card import Card


def make_card(year: int, deezer_id: int = 0) -> Card:
    return Card(
        deezer_id=deezer_id,
        title="Song",
        artist="Artist",
        release_year=year,
        preview_url="https://example.com/preview.mp3",
        album_art_url="https://example.com/art.jpg",
    )


def test_valid_slot_indices_empty_timeline():
    assert valid_slot_indices([]) == [0]


def test_valid_slot_indices_has_len_plus_one_gaps():
    timeline = [make_card(1990), make_card(2000), make_card(2010)]
    assert valid_slot_indices(timeline) == [0, 1, 2, 3]


def test_empty_timeline_first_card_is_trivially_correct():
    assert is_placement_correct([], slot_index=0, year=1975) is True


def test_correct_placement_between_two_cards():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=1, year=2000) is True


def test_incorrect_placement_between_two_cards():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=0, year=2000) is False


def test_correct_placement_at_start():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=0, year=1980) is True


def test_correct_placement_at_end():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=2, year=2020) is True


def test_tie_with_left_neighbor_counts_as_correct():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=1, year=1990) is True


def test_tie_with_right_neighbor_counts_as_correct():
    timeline = [make_card(1990), make_card(2010)]
    assert is_placement_correct(timeline, slot_index=1, year=2010) is True


def test_invalid_slot_index_raises():
    timeline = [make_card(1990), make_card(2010)]
    for bad_index in (-1, 3, 99):
        try:
            is_placement_correct(timeline, slot_index=bad_index, year=2000)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for slot_index={bad_index}")
