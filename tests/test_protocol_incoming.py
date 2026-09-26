import json

import pytest

from server.protocol.incoming import (
    CreateRoomMessage,
    FinishTurnMessage,
    InvalidIncomingMessageError,
    JoinRoomMessage,
    MashupPlacementMessage,
    MashupPreviewMessage,
    PlaceCardMessage,
    ReconnectMessage,
    SkipStealMessage,
    StartGameMessage,
    StealAttemptMessage,
    SwitchTrackMessage,
    UseHintMessage,
    parse_incoming,
)


def test_parse_create_room():
    msg = parse_incoming(json.dumps({"type": "create_room", "player_name": "Alice"}))
    assert isinstance(msg, CreateRoomMessage)
    assert msg.player_name == "Alice"


def test_parse_start_game():
    msg = parse_incoming(json.dumps({"type": "start_game"}))
    assert isinstance(msg, StartGameMessage)


def test_parse_join_room():
    msg = parse_incoming(json.dumps({"type": "join_room", "room_code": "ABCDE", "player_name": "Alice"}))
    assert isinstance(msg, JoinRoomMessage)
    assert msg.room_code == "ABCDE"
    assert msg.player_name == "Alice"


def test_parse_reconnect():
    msg = parse_incoming(json.dumps({"type": "reconnect", "reconnect_token": "tok123"}))
    assert isinstance(msg, ReconnectMessage)
    assert msg.reconnect_token == "tok123"


def test_parse_place_card_with_optional_guess():
    msg = parse_incoming(
        json.dumps(
            {
                "type": "place_card",
                "slot_index": 2,
                "guessed_artist": "The Beatles",
                "guessed_title": "Hey Jude",
            }
        )
    )
    assert isinstance(msg, PlaceCardMessage)
    assert msg.slot_index == 2
    assert msg.guessed_artist == "The Beatles"
    assert msg.guessed_title == "Hey Jude"


def test_parse_place_card_without_guess_defaults_to_none():
    msg = parse_incoming(json.dumps({"type": "place_card", "slot_index": 0}))
    assert isinstance(msg, PlaceCardMessage)
    assert msg.guessed_artist is None
    assert msg.guessed_title is None


def test_parse_finish_turn():
    msg = parse_incoming(json.dumps({"type": "finish_turn"}))
    assert isinstance(msg, FinishTurnMessage)


def test_parse_steal_attempt():
    msg = parse_incoming(json.dumps({"type": "steal_attempt", "target_player_id": "p1", "slot_index": 3}))
    assert isinstance(msg, StealAttemptMessage)
    assert msg.target_player_id == "p1"
    assert msg.slot_index == 3


def test_parse_skip_steal():
    msg = parse_incoming(json.dumps({"type": "skip_steal"}))
    assert isinstance(msg, SkipStealMessage)


def test_parse_use_hint():
    msg = parse_incoming(json.dumps({"type": "use_hint"}))
    assert isinstance(msg, UseHintMessage)


def test_parse_switch_track():
    msg = parse_incoming(json.dumps({"type": "switch_track"}))
    assert isinstance(msg, SwitchTrackMessage)


def test_parse_mashup_placement():
    msg = parse_incoming(json.dumps({"type": "mashup_placement", "guessed_year": 1998}))
    assert isinstance(msg, MashupPlacementMessage)
    assert msg.guessed_year == 1998


def test_parse_mashup_preview():
    msg = parse_incoming(json.dumps({"type": "mashup_preview", "guessed_year": 1998}))
    assert isinstance(msg, MashupPreviewMessage)
    assert msg.guessed_year == 1998


def test_malformed_json_raises_clear_error():
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming("{not valid json")


def test_missing_required_field_raises_clear_error():
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming(json.dumps({"type": "join_room", "room_code": "ABCDE"}))  # missing player_name


def test_unknown_type_raises_clear_error():
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming(json.dumps({"type": "teleport_player", "foo": "bar"}))


def test_missing_type_field_raises_clear_error():
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming(json.dumps({"room_code": "ABCDE", "player_name": "Alice"}))
