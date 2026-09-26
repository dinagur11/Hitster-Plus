"""GameRoom model — generic base shared by every room type.

Holds only room-lifecycle data common to TimelineRoom and BuzzerRoom. The
game-specific state machines (turn order, timelines, tokens, buzzer state,
...) are added in rooms/timeline_room.py and rooms/buzzer_room.py in a later
build step, not here.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from server.models.enums import RoomLifecycle
from server.models.player import Player


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class GameRoom:
    room_id: str
    theme: str | None = None
    lifecycle: RoomLifecycle = RoomLifecycle.LOBBY
    host_id: str | None = None
    players: list[Player] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
