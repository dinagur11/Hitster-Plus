// Matches server/main.py's HOST/PORT for local dev. No env-based override
// yet — not needed until this deploys anywhere but localhost.
export const WS_URL = "ws://localhost:8765";

// Mirror of server/config.py's timer constants. The server never sends a
// "total seconds" figure over the wire (only absolute deadlines — see
// wire/useCountdown.ts), so a countdown ring needs its total from
// somewhere; these are that somewhere. Keep in sync with server/config.py
// by hand — there's no shared source of truth across the language boundary.
export const TURN_SECONDS = 75;
export const STEAL_WINDOW_SECONDS = 40;
export const STEAL_WINDOW_SKIPPED_SECONDS = 15;
export const MAX_HINT_SLOTS = 3;
