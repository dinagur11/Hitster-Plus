class IllegalActionError(Exception):
    """A method call didn't match the room's current phase, turn, or rules."""


class RoomNotFoundError(Exception):
    """No room exists with the given code."""


class RoomNotJoinableError(Exception):
    """The room exists but isn't accepting new players right now."""


class InvalidReconnectTokenError(Exception):
    """The reconnect token doesn't match any active player.

    Covers an unknown token, a token whose grace period already expired, and
    a token whose room has since been garbage-collected — all the same
    clean rejection from the caller's point of view.
    """
