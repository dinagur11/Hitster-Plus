import random
from datetime import datetime, timedelta

import pytest

from server.config import CAPPED_WIN_TIMELINE_LENGTH, PLAYER_DISCONNECT_GRACE_SECONDS, ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH, WIN_TIMELINE_LENGTH
from server.models.card import Card
from server.models.enums import RoomLifecycle
from server.rooms.errors import InvalidReconnectTokenError, InvalidThemeError, RoomNotFoundError, RoomNotJoinableError
from server.rooms.room_manager import RoomManager

NOW = datetime(2026, 1, 1, 12, 0, 0)


class NeverMashup(random.Random):
    """Keeps round_type NORMAL — without this, a real (unseeded) rng can
    occasionally roll MASHUP on the first turn, which needs more cards than
    a small test deck provides, making the test flaky."""

    def random(self):
        return 0.999999


def test_create_room_returns_room_host_and_token():
    manager = RoomManager()
    room, host, token = manager.create_room("Alice")

    assert room.room_id in manager.rooms
    assert len(room.room_id) == ROOM_CODE_LENGTH
    assert all(c in ROOM_CODE_ALPHABET for c in room.room_id)
    assert room.lifecycle == RoomLifecycle.LOBBY
    assert room.host_id == host.player_id
    assert host.is_host is True
    assert room.players == [host]
    assert token == host.reconnect_token
    assert len(token) > 20


def test_create_room_populates_a_real_deck():
    """Regression test: TimelineRoom used to always start with an empty
    deck (nothing loaded it), so start_game failed for every real room."""
    manager = RoomManager()
    room, _, _ = manager.create_room("Alice")
    assert len(room.deck) > 0
    assert all(isinstance(c, Card) for c in room.deck)


def test_created_room_can_actually_start_game():
    manager = RoomManager()
    room, host, _ = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    room.rng = NeverMashup()

    room.start_game(NOW)  # would previously raise: deck doesn't have enough cards

    assert room.lifecycle == RoomLifecycle.IN_PROGRESS
    assert len(host.timeline) == 1  # dealt a starting card


def test_create_room_defaults_to_general_theme_and_win_length():
    manager = RoomManager()
    room, _, _ = manager.create_room("Alice")

    assert room.theme == "general"
    assert room.win_timeline_length == WIN_TIMELINE_LENGTH


@pytest.mark.parametrize("theme", ["rock", "pop"])
def test_create_room_with_themed_playlist_caps_win_length(theme):
    manager = RoomManager()
    room, _, _ = manager.create_room("Alice", theme=theme)

    assert room.theme == theme
    assert room.win_timeline_length == CAPPED_WIN_TIMELINE_LENGTH
    assert len(room.deck) > 0
    assert all(isinstance(c, Card) for c in room.deck)


def test_create_room_with_unknown_theme_raises():
    manager = RoomManager()
    with pytest.raises(InvalidThemeError):
        manager.create_room("Alice", theme="jazz")


def test_join_room_adds_player():
    manager = RoomManager()
    room, host, _ = manager.create_room("Alice")

    joined_room, player, token = manager.join_room(room.room_id, "Bob")

    assert joined_room is room
    assert player in room.players
    assert player.is_host is False
    assert player.reconnect_token == token
    assert len(room.players) == 2


def test_join_nonexistent_room_raises():
    manager = RoomManager()
    with pytest.raises(RoomNotFoundError):
        manager.join_room("ZZZZZ", "Bob")


def test_join_room_after_game_started_raises():
    manager = RoomManager()
    room, host, _ = manager.create_room("Alice")
    manager.join_room(room.room_id, "Bob")
    room.deck = [
        Card(deezer_id=1, title="Song", artist="Artist", release_year=2000,
             preview_url="https://x", album_art_url="https://y"),
        Card(deezer_id=2, title="Song2", artist="Artist2", release_year=1980,
             preview_url="https://x", album_art_url="https://y"),
        Card(deezer_id=3, title="Song3", artist="Artist3", release_year=1990,
             preview_url="https://x", album_art_url="https://y"),
    ]
    room.rng = NeverMashup()
    room.start_game(NOW)

    with pytest.raises(RoomNotJoinableError):
        manager.join_room(room.room_id, "Carol")


def test_room_code_collision_is_retried(monkeypatch):
    manager = RoomManager()
    manager.rooms["AAAAA"] = object()  # pre-occupy a code

    codes = iter(["AAAAA", "AAAAA", "BBBBB"])
    monkeypatch.setattr(manager, "_generate_room_code", lambda: next(codes))

    room, _, _ = manager.create_room("Alice")
    assert room.room_id == "BBBBB"


def test_all_players_disconnected_triggers_immediate_room_cleanup():
    manager = RoomManager()
    room, host, _ = manager.create_room("Alice")
    _, guest, _ = manager.join_room(room.room_id, "Bob")

    manager.mark_disconnected(room.room_id, host.player_id, NOW)
    assert room.room_id in manager.rooms  # Bob still connected

    manager.mark_disconnected(room.room_id, guest.player_id, NOW)
    assert room.room_id not in manager.rooms  # everyone gone -> immediate cleanup


def test_room_cleanup_also_purges_reconnect_tokens():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")

    manager.mark_disconnected(room.room_id, host.player_id, NOW)
    manager.mark_disconnected(room.room_id, guest.player_id, NOW)

    assert host_token not in manager._tokens
    assert guest_token not in manager._tokens


def test_reconnect_matches_token_and_restores_connected():
    manager = RoomManager()
    room, host, token = manager.create_room("Alice")
    _, guest, _ = manager.join_room(room.room_id, "Bob")
    manager.mark_disconnected(room.room_id, guest.player_id, NOW)  # host still connected, no cleanup

    reconnected_room, reconnected_player = manager.reconnect(guest.reconnect_token)

    assert reconnected_room is room
    assert reconnected_player is guest
    assert reconnected_player.connected is True
    assert reconnected_player.disconnected_at is None


def test_reconnect_with_unknown_token_fails_cleanly():
    manager = RoomManager()
    with pytest.raises(InvalidReconnectTokenError):
        manager.reconnect("not-a-real-token")


def test_reconnect_after_room_garbage_collected_fails_cleanly():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")

    manager.mark_disconnected(room.room_id, host.player_id, NOW)
    manager.mark_disconnected(room.room_id, guest.player_id, NOW)  # room now garbage-collected

    with pytest.raises(InvalidReconnectTokenError):
        manager.reconnect(guest_token)


def test_sweep_removes_player_after_grace_period_and_expires_their_token():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    _, guest, guest_token = manager.join_room(room.room_id, "Bob")
    manager.mark_disconnected(room.room_id, guest.player_id, NOW)

    just_before = NOW + timedelta(seconds=PLAYER_DISCONNECT_GRACE_SECONDS - 1)
    manager.sweep_expired_players(just_before)
    assert guest in room.players
    assert guest_token in manager._tokens

    just_after = NOW + timedelta(seconds=PLAYER_DISCONNECT_GRACE_SECONDS + 1)
    manager.sweep_expired_players(just_after)
    assert guest not in room.players
    assert guest_token not in manager._tokens
    assert room.room_id in manager.rooms  # host still present, room survives

    with pytest.raises(InvalidReconnectTokenError):
        manager.reconnect(guest_token)


def test_sweep_removes_room_if_last_player_expires():
    manager = RoomManager()
    room, host, host_token = manager.create_room("Alice")
    manager.mark_disconnected(room.room_id, host.player_id, NOW)

    manager.sweep_expired_players(NOW + timedelta(seconds=PLAYER_DISCONNECT_GRACE_SECONDS + 1))

    assert room.room_id not in manager.rooms
    assert host_token not in manager._tokens
