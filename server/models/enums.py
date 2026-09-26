"""Enums shared across models and room state machines.

Enums whose values are serialized into the wire protocol use ``str, Enum``
with explicit string values. Enums that never leave the server may use
``auto()`` instead (none needed yet at this layer).
"""

from enum import Enum


class RoomLifecycle(str, Enum):
    """Base GameRoom's phase — coarse, shared by every room type."""

    LOBBY = "lobby"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class TimelinePhase(str, Enum):
    """TimelineRoom's own turn-level state machine.

    Correctness (of the original placement and of every steal attempt) is
    never evaluated in real time. Steal attempts during STEAL_WINDOW are only
    recorded, not checked — nobody's outcome is known until PENDING_REVEAL,
    where the server evaluates the original placement and every recorded
    steal attempt together in one pass.

    Transitions:
        AWAITING_PLACEMENT --(finish_turn)--> STEAL_WINDOW
        STEAL_WINDOW --(timer expires or all valid slots attempted)--> PENDING_REVEAL
        PENDING_REVEAL --(server evaluates everything in one pass)--> REVEAL
        REVEAL --> ROUND_END

    STEAL_WINDOW always opens once "Finish Turn" is clicked — it is not
    conditional on the original placement being correct, since that isn't
    known yet at that point.
    """

    AWAITING_PLACEMENT = "awaiting_placement"
    STEAL_WINDOW = "steal_window"
    PENDING_REVEAL = "pending_reveal"
    REVEAL = "reveal"
    ROUND_END = "round_end"


class BuzzerPhase(str, Enum):
    """BuzzerRoom's own state machine — unrelated to TimelinePhase."""

    WAITING_FOR_ANSWERS = "waiting_for_answers"
    REVEALING = "revealing"
    ROUND_END = "round_end"


class RoundType(str, Enum):
    """Distinguishes a normal timeline turn from a once-per-player mashup turn."""

    NORMAL = "normal"
    MASHUP = "mashup"
