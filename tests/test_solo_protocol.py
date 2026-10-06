import json
from datetime import datetime

import pytest

from server.protocol.incoming import (
    InvalidIncomingMessageError,
    SoloFinishTurnMessage,
    SoloLeaveMessage,
    SoloStartMessage,
    SoloSwitchTrackMessage,
    SoloUseHintMessage,
    parse_incoming,
)
from server.protocol.solo_outgoing import build_solo_reveal, build_solo_started, build_solo_state
from tests.test_solo_room import NOW, correct, make_room, wrong

SECRET_FIELDS = ("title", "artist", "release_year", "album_art_url")


def all_messages(room):
    return [build_solo_started(room), build_solo_state(room)]


def upcoming_ids(room) -> set[int]:
    return {c.deezer_id for c in room.deck}


# -- incoming ---------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"type": "solo_start"}, SoloStartMessage),
        ({"type": "solo_finish_turn", "slot_index": 2}, SoloFinishTurnMessage),
        ({"type": "solo_use_hint"}, SoloUseHintMessage),
        ({"type": "solo_switch_track"}, SoloSwitchTrackMessage),
        ({"type": "solo_leave"}, SoloLeaveMessage),
    ],
)
def test_parses_solo_messages(payload, expected):
    assert isinstance(parse_incoming(json.dumps(payload)), expected)


def test_finish_turn_requires_a_non_negative_slot():
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming(json.dumps({"type": "solo_finish_turn"}))
    with pytest.raises(InvalidIncomingMessageError):
        parse_incoming(json.dumps({"type": "solo_finish_turn", "slot_index": -1}))


# -- outgoing: no leaks --------------------------------------------------------


def test_state_current_card_is_redacted():
    room = make_room()
    state = build_solo_state(room)
    assert set(state["current_card"]) == {"deezer_id", "preview_url"}


def test_no_upcoming_card_data_in_any_outgoing_message():
    room = make_room()
    secret_ids = upcoming_ids(room) - {room.current_card.deezer_id}
    # The deck's titles/artists are distinctive ("Queue N"/"QArtist N").
    for message in all_messages(room):
        text = json.dumps(message)
        assert "Queue " not in text and "QArtist" not in text
        for card_id in secret_ids:
            assert f'"deezer_id": {card_id}' not in text
    state = build_solo_state(room)
    assert "deck" not in state and "queue" not in state and "reserve" not in state
    assert state["switch_available"] is True  # a boolean, not the pool


def test_current_card_fields_never_reach_the_client_before_reveal():
    room = make_room()
    text = json.dumps(all_messages(room))
    card = room.current_card
    assert card.title == "Queue 0" and card.title not in text
    assert card.artist not in text
    assert f'"release_year": {card.release_year}' not in text
    assert card.album_art_url not in text


def test_timeline_cards_are_full_but_only_already_placed_ones():
    room = make_room()
    state = build_solo_state(room)
    assert [c["release_year"] for c in state["timeline"]] == [1980]
    assert set(state["timeline"][0]) >= set(SECRET_FIELDS)


def test_reveal_exposes_only_the_just_played_card():
    room = make_room()
    played = room.current_card
    correct(room)
    reveal = build_solo_reveal(room)
    assert reveal["card"]["deezer_id"] == played.deezer_id
    assert reveal["card"]["release_year"] == played.release_year
    assert reveal["outcome"] == "correct"
    leaked = upcoming_ids(room)
    text = json.dumps([reveal, build_solo_state(room)])
    for card_id in leaked:
        assert f'"deezer_id": {card_id}' not in text.replace(f'"deezer_id": {played.deezer_id}', "")


def test_state_hides_current_card_during_reveal_and_after_finish():
    room = make_room()
    wrong(room)
    state = build_solo_state(room)
    assert state["current_card"] is None
    assert state["phase"] == "reveal"
    assert state["strikes"] == 1


def test_grayed_out_slots_only_while_awaiting_placement():
    room = make_room()
    room.player.tokens = 1
    room.request_hint(NOW)
    assert build_solo_state(room)["grayed_out_slots"] == [0]
    correct(room)
    assert build_solo_state(room)["grayed_out_slots"] == []


def test_state_is_json_serializable():
    json.dumps(build_solo_state(make_room()))
    assert datetime.fromisoformat(build_solo_state(make_room())["turn_deadline"])
