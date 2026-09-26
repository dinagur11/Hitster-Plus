"""Timer lengths, token costs, and other tunable constants."""

TURN_SECONDS = 75
STEAL_WINDOW_SECONDS = 30
# Used instead of STEAL_WINDOW_SECONDS when nobody but the acting player
# has enough tokens to attempt a steal — there's nothing to wait for, but
# a brief, visible "skipped" beat is friendlier than jumping straight to
# reveal with no explanation.
STEAL_WINDOW_SKIPPED_SECONDS = 15
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
