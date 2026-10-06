# Hitster Clone — Project Context

## What this is

A browser-based multiplayer clone of the physical game Hitster (guess a song's
release year and place it on a shared timeline), built as a portfolio project.
Python backend (asyncio + websockets), React frontend. Original mechanics plus
custom additions: token economy, steal mechanic, hint system, a "mashup"
bonus round, and a replayable solo mode (play alone, no room code).

## Tech stack

- **Server:** Python 3.12+, `asyncio`, `websockets` library (raw WebSockets,
  not Socket.IO). Optionally FastAPI later for lobby/HTTP endpoints alongside
  the WebSocket game connection — not needed for v1.
- **Client:** React (Vite) + plain CSS (or CSS modules) — no CSS-in-JS
  framework, no Canvas. Timeline and cards render as styled DOM elements.
- **Track data/audio:** the iTunes Search API (free, no key; 30s preview clips
  + metadata: title, artist, release year, album art). Decks are built
  offline by `build_general_deck.py`, which resolves a curated `*_seed.json`
  into the playable `general.json` / `rock.json` / `pop.json`; the server
  only ever reads those static files. Do **not** use Spotify's `preview_url`
  — it's deprecated and returns null for API clients as of late 2024/2026.
  No self-hosted audio, no licensing cost. (`Card.deezer_id` is a leftover
  name from the originally planned Deezer source; it actually holds the
  iTunes track id. Renaming it is a separate, not-yet-requested change.)
- **State storage:** in-memory only for v1. A single Python process holds
  `dict[room_id, GameRoom]`. No database, no Redis. Do not add persistence
  infrastructure unless explicitly asked — it's out of scope for v1.

## Architecture

Two independent room types, both subclasses of the pure-data `GameRoom`, not
variants of one state machine:

- **Multiplayer** (`TimelineRoom`) — the main game: turns, timelines, tokens,
  steal mechanic, mashup rounds. Created and tracked by `RoomManager`.
- **Solo** (`SoloRoom`) — solo mode: one player, no turn order, no
  steal window, no mashup rounds; strikes and a 15-correct win. Has its own
  phase enum (`SoloPhase`) and its own handler (`solo_handler.py`); it is not
  stored in `RoomManager`. Shares only the `Card`/`Player` models, the
  `game_logic` functions (`placement`, `hints`, `guess_matching`) and the
  websocket plumbing with `TimelineRoom`. Do not merge the two into one
  state machine or add solo flags to `TimelineRoom`.

Server is authoritative for all game state. Clients never compute correctness,
never compute which timeline slots are valid/invalid (that would leak
answers), and always re-render from server-pushed `state_update` messages
rather than deriving state locally.

### Module layout

```
server/
  main.py                # thin entrypoint: starts websockets.serve() loop
  config.py              # timer lengths, token costs, win lengths, solo constants
  models/                # Card, Player, GameRoom, enums — pure data, no rule logic
    enums.py              # RoomLifecycle, TimelinePhase, SoloPhase, SoloResult, RoundType
  rooms/
    room_manager.py       # dict[room_id, TimelineRoom], create/join/cleanup
    timeline_room.py       # multiplayer state machine
    solo_room.py            # solo-mode state machine
    errors.py                # IllegalActionError and friends
  protocol/
    incoming.py            # parse/validate client→server JSON (Pydantic), incl. solo_* messages
    outgoing.py             # build server→client JSON for multiplayer rooms
    solo_outgoing.py         # build server→client JSON for solo runs
  deck/
    loader.py               # loads a theme's deck (general/rock/pop) into list[Card]
  game_logic/
    placement.py            # timeline correctness checks
    steal.py                 # per-slot steal contention/locking
    hints.py                  # hint slot computation → grayed-out slots
    mashup.py                  # mashup round scoring (±10yr check)
    turn_manager.py             # round type decisions, turn advance, timers
    guess_matching.py           # fuzzy artist/title guess matching (rapidfuzz)
  ws_handler.py                 # per-connection recv loop, dispatch to multiplayer rooms
  solo_handler.py                # solo sessions per connection + their deadline timers
client/                          # React (Vite) app; src/components/, src/wire/
tests/                           # pytest; game_logic and rooms tested without websockets
general.json rock.json pop.json  # playable decks (repo root), built by build_general_deck.py
general_deck_seed.json ...       # curated seeds the build script resolves via iTunes
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

**Hints:** Each hint request spends `HINT_TOKEN_COST_PER_SLOT` (1) token and
grays out one more incorrect timeline slot (server-computed only — never let
the client determine which slots are wrong). Repeatable, up to
`MAX_HINT_SLOTS` (3) per turn, fewer if fewer incorrect slots exist (the
correct slot can never be grayed). Only usable during `AWAITING_PLACEMENT`,
before `finish_turn` locks placement in; only offered during `NORMAL`
rounds, not `MASHUP` (no discrete slot set to gray out there).

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

**Solo mode (`SoloRoom`):** a single player can start a run from the home
screen with no room code, and can play as many runs as they like. Settled rules:

- Deck: at `start`, the room shuffles a copy of the `general` deck using its
  injectable `rng` (Fisher-Yates over `rng.randrange`, same pattern and reason
  as `TimelineRoom._deal_starting_cards`, so tests can make it deterministic).
  The first card is the starting card; each turn draws the next card in order.
  A deck smaller than `SOLO_MIN_DECK_SIZE` (1 starting card + 17 placements,
  the most a run can take, + `SOLO_SWITCH_BUFFER` spare cards for switches) is
  refused with a clear error.
- Start: the player begins with one revealed card on their timeline (same as
  the multiplayer starting card). Starting tokens are 0, same as multiplayer.
- Loop: hear a song, place it into a slot (slot-snapping `NormalTimeline`,
  `game_logic/placement.py`), optionally guess artist/title, click Finish
  Turn, reveal. Re-dragging is client-local; one `solo_finish_turn` message
  carries the slot and guess.
- Correct placement: the card joins the timeline. Incorrect placement: the
  card is discarded and the player gets a **strike**. Turn timeout
  (`TURN_SECONDS`) counts as an incorrect placement, so it is also a strike.
- Win: 15 correct placements (`SOLO_WIN_CORRECT`; the starting card does not
  count). Lose: the 3rd strike (`SOLO_MAX_STRIKES`) ends the run immediately.
  The final reveal still plays before the end screen.
- Guess bonus: identical to multiplayer (`guess_matching`, `GUESS_BONUS_TOKENS`),
  independent of placement correctness.
- Tokens are only spent on hint (same rules and cost as multiplayer) and
  switch track (`SWITCH_TRACK_TOKEN_COST`, once per turn, resets the timer,
  clears that turn's grayed slots; draws the next card from the shuffled
  deck). No steal window, no steal phases/messages, no mashup rounds.
- End screen: final timeline, result, correct count out of 15, strikes used,
  a "Copy result" button (mode name, correct/15, per-turn sequence of correct
  placements and strikes), "Play again" (a fresh `solo_start`, new random
  deck; the server replaces a finished session) and a way back home.
- Disconnecting forfeits the run: no reconnect token, no grace period.
- Server is authoritative and never sends upcoming cards or the current
  card's title/artist/year/art before its reveal (only a redacted card).
  `solo_state.switch_available` is a boolean, not the deck. No dates, no
  `localStorage`, no server persistence, consistent with the no-DB rule.

**Disconnection handling (multiplayer):** No special pause/grace logic mid-turn — the
existing 75s timer already absorbs brief drops; if it expires before
reconnect, resolve as a failed/skipped turn as normal. Outside of turns, use
a grace period (~60s) before removing a disconnected player. If **all**
players in a room disconnect, garbage-collect the room immediately — no grace
period at the room level.

**Deck:** static JSON files per theme (`general.json`, `rock.json`,
`pop.json` at the repo root), loaded by `deck/loader.py` into `list[Card]`.
Custom/user-uploaded decks are a later feature, not v1.

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

## Deferred to later versions

Optional ideas, not planned:

- A daily challenge: same solo rules, but cards ordered by sorting the deck on
  `sha256(f"{date}:{theme}:{track_id}")` with a server-side UTC date, plus a
  once-per-day limit.
- A streak counter.

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