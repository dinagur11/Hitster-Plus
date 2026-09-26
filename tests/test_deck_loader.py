import pytest

from server.deck.loader import load_theme
from server.models.card import Card


def test_load_theme_returns_cards():
    deck = load_theme("general")
    assert len(deck) > 0
    assert all(isinstance(card, Card) for card in deck)


def test_load_theme_maps_fields_correctly():
    deck = load_theme("general")
    card = deck[0]
    assert isinstance(card.deezer_id, int)
    assert isinstance(card.title, str) and card.title
    assert isinstance(card.artist, str) and card.artist
    assert isinstance(card.release_year, int)
    assert card.preview_url.startswith("http")
    assert card.album_art_url.startswith("http")


def test_load_theme_defaults_to_general():
    assert load_theme() == load_theme("general")


def test_load_theme_rejects_unknown_theme():
    with pytest.raises(ValueError):
        load_theme("nonexistent-theme")


def test_load_theme_returns_a_fresh_list_each_call():
    """Callers (e.g. RoomManager.create_room) shuffle this list in place —
    it must not be a shared mutable object across rooms."""
    deck_a = load_theme("general")
    deck_b = load_theme("general")
    assert deck_a is not deck_b
    deck_a.pop()
    assert len(deck_a) != len(deck_b)
