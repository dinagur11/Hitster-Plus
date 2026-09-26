"""Player model.

Timeline-game state (tokens, timeline, mashup usage) lives directly on
Player rather than a Timeline-specific subclass, per project decision.
BuzzerRoom doesn't use these fields; it tracks its own per-player score
separately in its own room state.

The network connection is represented as an opaque id rather than a live
websocket object, so this module stays asyncio-free and easily constructible
in unit tests. ws_handler.py owns the actual dict[connection_id, WebSocket].
"""

from dataclasses import dataclass, field
from datetime import datetime

from server.models.card import Card


@dataclass
class Player:
    player_id: str
    name: str
    connection_id: str | None = None
    connected: bool = True
    is_host: bool = False
    tokens: int = 0
    timeline: list[Card] = field(default_factory=list)
    had_mashup_round: bool = False
    reconnect_token: str | None = None
    disconnected_at: datetime | None = None
