"""Timer lengths, token costs, and other tunable constants."""

TURN_SECONDS = 75
STEAL_WINDOW_SECONDS = 30
# Used instead of STEAL_WINDOW_SECONDS when nobody but the acting player
# has enough tokens to attempt a steal — there's nothing to wait for, but
# a brief, visible "skipped" beat is friendlier than jumping straight to
# reveal with no explanation.
STEAL_WINDOW_SKIPPED_SECONDS = 7
# Once every valid slot has been attempted (right or wrong — correctness
# isn't checked yet), the window has nothing left to wait ON, but still
# holds for this long before revealing, so every player actually gets to
# see who claimed which slot rather than the window vanishing the instant
# the last attempt lands.
STEAL_WINDOW_ALL_ATTEMPTED_DELAY_SECONDS = 10
# Same idea, but for the "everyone who could steal explicitly passed"
# case: shorter than the all-attempted delay since there's nothing left
# to actually look at (no attempt badges to see), just a quick beat to
# confirm nobody's stealing before moving on.
STEAL_WINDOW_ALL_SKIPPED_DELAY_SECONDS = 5

# How long REVEAL holds before the server itself advances to the next turn
# (or, if this reveal was the winning one, before it stops mattering) — a
# real, server-held deadline like turn_deadline/steal_deadline, not a
# client-side auto-continue.
REVEAL_SECONDS = 9

# First player to reach this many cards on their own timeline wins the
# game outright — per CLAUDE.md's settled win condition. This is the
# "general" theme's win length; a themed (non-general) deck is smaller, so
# it caps at CAPPED_WIN_TIMELINE_LENGTH instead — see
# RoomManager.create_room, which picks between the two by theme name.
WIN_TIMELINE_LENGTH = 10
CAPPED_WIN_TIMELINE_LENGTH = 5

MAX_HINT_SLOTS = 3
HINT_TOKEN_COST_PER_SLOT = 1
STEAL_TOKEN_COST = 1
GUESS_BONUS_TOKENS = 1
MASHUP_EXACT_YEAR_BONUS_TOKENS = 1
SWITCH_TRACK_TOKEN_COST = 1

PLAYER_DISCONNECT_GRACE_SECONDS = 60

ROOM_CODE_LENGTH = 5
# Excludes visually ambiguous characters: 0/O, 1/I.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# How often ws_handler polls RoomManager.sweep_expired_players. Independent
# of PLAYER_DISCONNECT_GRACE_SECONDS itself — just polling granularity.
DISCONNECT_SWEEP_INTERVAL_SECONDS = 10

# -- Solo daily challenge (see game_logic/daily.py, rooms/solo_room.py) ----

# Correct placements needed to win a run (the seeded starting card doesn't count).
SOLO_WIN_CORRECT = 15
# The 3rd strike ends the run immediately.
SOLO_MAX_STRIKES = 3
# 15 to win + up to (SOLO_MAX_STRIKES - 1) non-final strikes = 17 placements
# at most, so every possible run fits in the main queue.
SOLO_MAIN_QUEUE_SIZE = SOLO_WIN_CORRECT + SOLO_MAX_STRIKES - 1
# A deck must hold start + main queue + at least this many reserve cards
# (consumed in order by switch-track), or a solo session is refused.
SOLO_MIN_RESERVE_CARDS = 5
