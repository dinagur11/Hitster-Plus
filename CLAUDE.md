# Hitster Clone — Project Context

## What this is

A browser-based multiplayer clone of the physical game Hitster (guess a song's
release year and place it on a shared timeline), built as a portfolio project.
Python backend (asyncio + websockets), React frontend. Original mechanics plus
custom additions: token economy, steal mechanic, hint system, and a "mashup"
bonus round.

## Tech stack

- **Server:** Python 3.12+, `asyncio`, `websockets` library (raw WebSockets,
  not Socket.IO). Optionally FastAPI later for lobby/HTTP endpoints alongside
  the WebSocket game connection — not needed for v1.
- **Client:** React (Vite) + plain CSS (or CSS modules) — no CSS-in-JS
  framework, no Canvas. Timeline and cards render as styled DOM elements.
- **Track data/audio:** Deezer's public preview API (30s clips + metadata:
  title, artist, release date, album art). Do **not** use Spotify's
  `preview_url` — it's deprecated and returns null for API clients as of
  late 2024/2026. No self-hosted audio, no licensing cost.
- **State storage:** in-memory only for v1. A single Python process holds
  `dict[room_id, GameRoom]`. No database, no Redis. Do not add persistence
  infrastructure unless explicitly asked — it's out of scope for v1.

## Architecture

Two independent game types, not variants of one state machine:

- **Timeline game** (`TimelineRoom`) — the main game: turns, timelines, tokens,
  steal mechanic, mashup rounds.
- **Buzzer game** (`BuzzerRoom`) — separate, simpler mode (guess-the-artist,
  first-to-answer). Shares only the `Card` model and connection plumbing with
  `TimelineRoom`. Do not merge these into one state machine.

Server is authoritative for all game state. Clients never compute correctness,
never compute which timeline slots are valid/invalid (that would leak
answers), and always re-render from server-pushed `state_update` messages
rather than deriving state locally.

### Module layout

```
server/
  main.py                # thin entrypoint: starts websockets.serve() loop
  config.py              # timer lengths, steal window, hint costs, etc.
  models/                # Card, Player, GameRoom, enums — pure data, no rule logic
  rooms/
    room_manager.py       # dict[room_id, GameRoom], create/join/cleanup
    timeline_room.py       # main game state machine
    buzzer_room.py         # buzzer mode state machine
  protocol/
    incoming.py            # parse/validate client→server JSON (Pydantic)
    outgoing.py             # build server→client JSON
  deck/
    loader.py               # loads theme JSON into list[Card]
    track_provider.py       # Deezer API calls (search, preview, art, year)
  game_logic/
    placement.py            # timeline correctness checks
    steal.py                 # per-slot steal contention/locking
    hints.py                  # hint tokens → grayed-out slot computation
    mashup.py                  # mashup round scoring (±10yr check)
    turn_manager.py             # round type decisions, turn advance, timers
    guess_matching.py           # fuzzy artist/title guess matching (rapidfuzz)
  ws_handler.py                 # per-connection recv loop, dispatch to rooms
tests/
```

Rule of thumb: `models/` never contains game-rule logic; `game_logic/`
functions take typed objects and return decisions, and should be unit
testable without any websocket/asyncio machinery. `protocol/` is the only
layer that touches raw JSON/dicts.

## Confirmed game design decisions

Treat these as settled requirements, not open questions — implement to spec,
don't relitigate unless something is actually broken:

**Win condition & player count:** First player to reach 10 cards on their
timeline wins. Up to 6 players per room.

**Core loop:** turn-based. Each player begins the game with one random card
from the deck already placed on their timeline, fully revealed (title,
artist, year all visible) — this is dealt once at `start_game`, before the
first turn, and is why a player's timeline is never actually empty when a
real placement occurs (minimum length 1, so there are always at least 2
valid slots — the seeded original's slot plus at least one stealable one —
from the very first turn onward). After that: player hears a song, drags it
onto their personal timeline, optionally types an artist/title guess,
clicks "Finish Turn" to lock it in (placement is freely re-draggable before
that). No round ends until "Finish Turn" is clicked.

**Timing:** 75 seconds total per turn (visible countdown on screen), covering
listening + placement + optional guess, as one shared pool — not split into
phases. Steal window after placement: 30–45s.

**Steal mechanic:** After a correct placement, other players may attempt to
steal by placing into a *specific slot* (gap) in the acting player's
timeline. Each slot can only be attempted by one player per round — once a
slot is attempted (right or wrong), it's locked for the rest of that window.
Different players may attempt different slots simultaneously. Stealing costs
a token.

**Hints:** Spend 1–3 tokens to gray out 1–3 incorrect timeline slots
(server-computed only — never let the client determine which slots are
wrong). Only usable during `AWAITING_PLACEMENT`, before `finish_turn` locks
placement in; one hint request per turn (spend 1/2/3 tokens in a single
action, no incremental top-ups); only offered during `NORMAL` rounds, not
`MASHUP` (no discrete slot set to gray out there).

**Track switch:** Spend 1 token to discard the current song and draw a
replacement, once per turn. Normal rounds only (not usable during a mashup
round). Only usable during `AWAITING_PLACEMENT`, before `finish_turn`.
Resets the turn timer to a fresh 75s. The discarded card goes to `discard`
(won't reappear this game). If the deck is empty when a switch is
attempted, reject cleanly with no token spent — don't crash.

**Artist/title guess bonus:** Guessing both correctly earns a token.

**Mashup round:** Happens exactly once per player, at a random point during
their own turn (probability should increase as the game nears its end so it's
guaranteed to trigger before a player's turns run out). 1 song, 15s clip.
Player places the song directly at its guessed *year* on the timeline (not
relative ordering) — within ±10 years of the real year = card kept; an exact
year guess additionally earns a bonus token. No steal mechanic on this round.
All artist/title/year info is revealed at the end regardless of outcome.

**Disconnection handling:** No special pause/grace logic mid-turn — the
existing 75s timer already absorbs brief drops; if it expires before
reconnect, resolve as a failed/skipped turn as normal. Outside of turns, use
a grace period (~60s) before removing a disconnected player. If **all**
players in a room disconnect, garbage-collect the room immediately — no grace
period at the room level.

**Deck:** JSON files per theme (`deck/themes/*.json`), loaded into
`list[Card]`. Custom/user-uploaded decks are a later feature, not v1.

**Storage — deliberately not AWS yet.** v1 has no database and no AWS
dependency: track data is static per-theme JSON files, checked into the
repo, no infra needed. Don't introduce DynamoDB, S3, or any AWS SDK calls
for the deck system until custom/user-generated decks (playlist import) are
actually being built — static files are the right amount of complexity
until then, and adding a database earlier would be unnecessary complexity
for data that's just author-curated config. Keep `deck/loader.py`'s
interface deck-source-agnostic (return `list[Card]` given a deck
identifier) so swapping the backing store later only touches that file's
internals, not its callers.

**AWS direction, when it's time:** DynamoDB for decks/cards (single-table
design: `DECK#<deck_id>` partition, `CARD#<track_id>` sort key, plus a
`USER#<user_id>` partition for user-owned custom decks) alongside Cognito
for user accounts/auth (validate JWTs on websocket connect rather than
building custom session logic). Both come in together, at the same point
user accounts are added — not before.

**Artist/title guess matching:** Not exact string match — use `rapidfuzz`
(`pip install rapidfuzz`). Normalize both strings first (lowercase, strip
punctuation, strip parenthetical tags like "(feat. X)"/"(Remastered)", strip
leading "the/a/an"), then score with `fuzz.ratio` (or `token_sort_ratio` for
multi-word titles where word order might vary). Threshold ~85 as a starting
point, tune once real deck data exists. Artist and title should have
separate matching calls/thresholds — artist names are shorter and more prone
to false-accepts (e.g. "Drake" vs "Blake"), so may need a stricter threshold
or a minimum-length guard.

## Frontend design direction

Retro vinyl / analog radio aesthetic, desktop-first (players are on their
own computers, not shared-screen).

**Color tokens:**
- Vinyl ink `#1B1712` — dominant dark surface (warm/walnut-tinted, not flat black)
- Aged label paper `#EDE3CF` — card surfaces, panels
- Walnut `#5C3D26` — structural borders/dividers
- Brass `#B08D57` — accents, token iconography, hardware details
- Dial amber `#E8A33D` — active states, the "lit up" highlight color
- Felt green `#2F4A3D` — secondary/success accent, used sparingly

**Type:** Fraunces (display/headline + the year numerals on the timeline —
this is the single most-stared-at UI element, it deserves personality, not
a system font) + Public Sans (body/UI/labels). Two families, clearly
distinct roles, nothing else.

**Avoid:** ALL-CAPS labels, monospace fonts for data labels, middle-dot-joined
meta strings (`A • B • C`), tracked-out eyebrow labels, "→" appended to
buttons/links — these are generic-AI-design tells, not stylistic choices,
even though they can superficially look "techy/retro."

**Keep from the working mockup:** the spinning vinyl record with tonearm,
the analog VU/countdown-ring timer, the warm dark palette and general mood.
These fit the brief well.

**Critical timeline correction — two different components needed:**
- **Normal rounds:** NOT a continuous year slider. The player places a card
  into one of the discrete gaps between their already-placed cards (`len(
  timeline) + 1` slots — see `game_logic/placement.py`). Visually this
  should be a slot-snapping variant of the timeline rail — existing cards
  pinned in place, drop zones between/before/after them, no free-floating
  continuous drag.
- **Mashup rounds only:** a continuous absolute-year dial/slider (drag
  anywhere along a year range, not snapped to slots) IS correct here — this
  is literally the mashup mechanic (guess a year, ±10 tolerance). The
  vinyl-dial slider component from the original mockup is a good fit for
  this round type specifically, not for normal rounds.

**Also needed but not yet designed:** steal-window UI (an opponent's
timeline with the locked original slot and open stealable slots), hint UI
(graying out incorrect slots), and the corrected reveal timing — locking in
a placement opens the steal window first; nothing gets evaluated or
revealed until after that window closes (`PENDING_REVEAL` → `REVEAL`), so
no immediate "locked in, here's your score" moment on click.

## Build order (don't skip ahead)

1. `models/` — dataclasses and enums only, no logic
2. `game_logic/placement.py`, `steal.py`, `mashup.py` + unit tests — prove
   rules work in isolation before any networking exists
3. `rooms/timeline_room.py` — wire the state machine, still test via direct
   method calls, no websockets yet
4. `protocol/` + `ws_handler.py` — networking last, once logic is proven

## Conventions

- Type hints everywhere; dataclasses for all models.
- `Enum` subclasses use `str, Enum` with explicit string values (not `auto()`)
  when the value gets serialized into the wire protocol — e.g. `RoundType`,
  `GamePhase`. Use `auto()` only for enums that never leave the server.
- Every state-changing message handler must check `room.phase` (or the
  equivalent room-specific phase) before acting, and reject anything that
  doesn't match. This is the primary defense against state-desync bugs —
  don't bypass it "just this once" for convenience.
- Server never trusts client-reported correctness, timing, or slot validity.
  All of that is computed server-side, always.