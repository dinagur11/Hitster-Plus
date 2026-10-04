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
        REVEAL --(reveal_deadline expires)--> ROUND_END

    STEAL_WINDOW always opens once "Finish Turn" is clicked — it is not
    conditional on the original placement being correct, since that isn't
    known yet at that point.
    """

    AWAITING_PLACEMENT = "awaiting_placement"
    STEAL_WINDOW = "steal_window"
    PENDING_REVEAL = "pending_reveal"
    REVEAL = "reveal"
    ROUND_END = "round_end"


class SoloPhase(str, Enum):
    """SoloRoom's own two-step turn loop — unrelated to TimelinePhase.

    Transitions:
        AWAITING_PLACEMENT --(finish_turn, or turn timer expiring)--> REVEAL
        REVEAL --(reveal_deadline expires)--> AWAITING_PLACEMENT (next turn),
            or stays put with lifecycle FINISHED once the run has ended.

    There's no steal window: the placement is evaluated the moment it's
    locked in.
    """

    AWAITING_PLACEMENT = "awaiting_placement"
    REVEAL = "reveal"


class SoloResult(str, Enum):
    """How a finished SoloRoom run ended."""

    WON = "won"
    OUT_OF_STRIKES = "out_of_strikes"


class RoundType(str, Enum):
    """Distinguishes a normal timeline turn from a once-per-player mashup turn."""

    NORMAL = "normal"
    MASHUP = "mashup"
