"""Client -> server message parsing.

Pydantic models per CLAUDE.md's conventions. This is the only layer that
touches raw JSON/dicts: `parse_incoming` takes a raw JSON string and
returns one of the typed message models below, dispatched on a `type`
discriminator field — never a bare dict, and never lets a malformed or
unknown message crash the caller.

`finish_turn` carries no fields: per CLAUDE.md's core loop, placement is
freely re-draggable via repeated `place_card` messages (which do carry the
slot/guess), and "Finish Turn" just locks in whatever the most recently
received `place_card` said — it isn't a second, independent submission.
"""

import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class InvalidIncomingMessageError(Exception):
    """Raised for malformed JSON, a missing/invalid field, or an unknown message type."""


class ListThemesMessage(BaseModel):
    """No fields: asks the server which deck/playlist themes are actually
    playable right now (see server/deck/loader.py's available_themes) —
    sent by the client's create-room screen so it only ever offers a
    playlist it can actually start a room with."""

    type: Literal["list_themes"] = "list_themes"


class CreateRoomMessage(BaseModel):
    type: Literal["create_room"] = "create_room"
    player_name: str
    # Deck/playlist to play with ("general", "rock", "pop", ...). None
    # defaults to "general" in RoomManager.create_room — validated there,
    # not here, since the set of known themes is deck/loader.py's concern.
    theme: str | None = None


class StartGameMessage(BaseModel):
    type: Literal["start_game"] = "start_game"


class JoinRoomMessage(BaseModel):
    type: Literal["join_room"] = "join_room"
    room_code: str
    player_name: str


class ReconnectMessage(BaseModel):
    type: Literal["reconnect"] = "reconnect"
    reconnect_token: str


class PlaceCardMessage(BaseModel):
    type: Literal["place_card"] = "place_card"
    slot_index: int = Field(ge=0)
    guessed_artist: str | None = None
    guessed_title: str | None = None


class FinishTurnMessage(BaseModel):
    type: Literal["finish_turn"] = "finish_turn"


class StealAttemptMessage(BaseModel):
    type: Literal["steal_attempt"] = "steal_attempt"
    target_player_id: str
    slot_index: int = Field(ge=0)


class SkipStealMessage(BaseModel):
    """No fields: a non-acting player explicitly declining to attempt a
    steal this window. Free (no token cost), and doesn't lock them out of
    attempting later — see TimelineRoom.skip_steal."""

    type: Literal["skip_steal"] = "skip_steal"


class UseHintMessage(BaseModel):
    """No fields: a hint request is a single click's worth — one token, one
    additional grayed-out slot, repeatable up to MAX_HINT_SLOTS per turn.
    See TimelineRoom.request_hint."""

    type: Literal["use_hint"] = "use_hint"


class SwitchTrackMessage(BaseModel):
    type: Literal["switch_track"] = "switch_track"


class MashupPlacementMessage(BaseModel):
    type: Literal["mashup_placement"] = "mashup_placement"
    guessed_year: int


class MashupPreviewMessage(BaseModel):
    """The mashup dial's tentative position — sent once the dial is
    released on a new value, not on every drag tick (that debouncing is
    the client's job; the server just broadcasts whatever it's sent, same
    as place_card's live preview does for the normal round)."""

    type: Literal["mashup_preview"] = "mashup_preview"
    guessed_year: int


IncomingMessage = Annotated[
    Union[
        ListThemesMessage,
        CreateRoomMessage,
        StartGameMessage,
        JoinRoomMessage,
        ReconnectMessage,
        PlaceCardMessage,
        FinishTurnMessage,
        StealAttemptMessage,
        SkipStealMessage,
        UseHintMessage,
        SwitchTrackMessage,
        MashupPlacementMessage,
        MashupPreviewMessage,
    ],
    Field(discriminator="type"),
]

_incoming_adapter: TypeAdapter[IncomingMessage] = TypeAdapter(IncomingMessage)


def parse_incoming(raw_json: str) -> IncomingMessage:
    """Parse a raw JSON string into its typed incoming message model.

    Raises InvalidIncomingMessageError for malformed JSON, an unrecognized
    `type`, or a message missing/misshaping required fields.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise InvalidIncomingMessageError(f"malformed JSON: {exc}") from exc

    try:
        return _incoming_adapter.validate_python(data)
    except ValidationError as exc:
        raise InvalidIncomingMessageError(str(exc)) from exc
