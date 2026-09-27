// Set via client/.env.local for local dev (see VITE_WS_URL there) —
// env-based so this can point somewhere other than localhost once deployed.
export const WS_URL = import.meta.env.VITE_WS_URL;

// Mirror of server/config.py's timer constants. The server never sends a
// "total seconds" figure over the wire (only absolute deadlines — see
// wire/useCountdown.ts), so a countdown ring needs its total from
// somewhere; these are that somewhere. Keep in sync with server/config.py
// by hand — there's no shared source of truth across the language boundary.
export const TURN_SECONDS = 75;
export const STEAL_WINDOW_SECONDS = 40;
export const STEAL_WINDOW_SKIPPED_SECONDS = 7;
export const REVEAL_SECONDS = 10;
export const MAX_HINT_SLOTS = 3;
