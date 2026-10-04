"""GameRoom model — generic base shared by every room type.

Holds only room-lifecycle data common to TimelineRoom and SoloRoom. The
game-specific state machines (turn order, steal windows, strikes, ...) live
in rooms/timeline_room.py and rooms/solo_room.py, not here.
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
