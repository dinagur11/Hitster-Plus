# Hitster+

A browser-based multiplayer clone of the physical game Hitster — guess a
song's release year and place it on your own shared timeline — plus a
few original additions: a token economy, a steal mechanic, hints, a
year-dial bonus round, and a solo daily challenge you can play right away.

Python (`asyncio` + raw `websockets`) on the server, React (Vite) on the
client. The server is authoritative for all game state; clients only
render what it pushes and never compute correctness themselves.

## Play alone: the Daily challenge

No room code and no other players needed: click **Daily challenge** on the
home screen and you're playing in a second. Everyone gets the same songs in
the same order each day (the date is the server's UTC date), and each browser
gets one attempt per day.

- Place each song on your timeline as usual, optionally guess the artist and
  title for a bonus token, and click Finish Turn.
- A wrong placement, or running out of the 75 seconds, costs a **strike**.
- **15 correct placements win** the run (your starting card doesn't count).
  **The 3rd strike ends it** immediately.
- Tokens from correct artist/title guesses can be spent on a hint or a track
  switch. There's no steal window and no Dial Round.
- When the run ends you get a result screen and a "Copy result" button that
  copies a shareable summary (date, correct out of 15, and a green/red
  sequence of your turns).

Your daily attempt is remembered in your browser's `localStorage`, nothing is
stored on the server. Closing the tab mid-run forfeits it, and the Daily
challenge button stays disabled until the next UTC day.

## How to play (multiplayer)

Build a timeline of songs in the right chronological order. First player
to 10 cards wins (5 on a themed Rock/Pop playlist, since those decks are
smaller). Every turn: hear a song, drag it onto a gap in your timeline,
optionally guess the artist/title for a bonus token, and click Finish
Turn. Once you finish, everyone else gets a short window to try stealing
the same card into their own timeline for a token. Once per game, one of
your turns becomes a Dial Round instead — guess the exact release year on
a dial rather than picking a gap. The full rundown is in the app itself,
under "How to play" on the home screen.

## Project layout

```
server/
  main.py                # entrypoint — starts the websockets.serve() loop
  config.py               # timer lengths, token costs, win length, etc.
  models/                 # Card, Player, GameRoom, enums — pure data
  rooms/
    room_manager.py        # dict[room_id, TimelineRoom], create/join/cleanup
    timeline_room.py        # the multiplayer game's turn-based state machine
    solo_room.py             # the solo daily-challenge state machine
  protocol/
    incoming.py             # client -> server message parsing (Pydantic)
    outgoing.py              # server -> client message building (multiplayer)
    solo_outgoing.py          # server -> client message building (solo runs)
  deck/
    loader.py                # loads a theme's deck (general/rock/pop) into list[Card]
  game_logic/
    placement.py              # timeline correctness checks
    steal.py                   # steal-window slot contention
    hints.py                    # hint tokens -> grayed-out slot computation
    mashup.py                    # dial-round (mashup) scoring
    turn_manager.py               # round-type decisions, turn advance, deadlines
    guess_matching.py             # fuzzy artist/title guess matching
    daily.py                       # deterministic daily deck order (sha256 of date:theme:track)
  ws_handler.py                   # per-connection recv loop, dispatch, broadcast
  solo_handler.py                  # solo sessions per connection + their timers

client/
  src/
    components/            # one folder per UI component (+ its .css)
    wire/                  # websocket connection + client<->server message types
    types.ts               # view-level TypeScript types

tests/                     # pytest — game_logic and rooms are unit-tested
                            # standalone (no websocket/asyncio needed)
```

## Running it locally

### Server

Run from the repo root — `server` is a package, and `main.py` is invoked
as a module (`python -m server.main`) rather than run as a script:

```
python -m venv venv && source venv/bin/activate   # or your own venv
pip install -r server/requirements.txt
python -m server.main
```

Listens on `ws://localhost:8765` by default (set `PORT` to override — used
by Railway/similar PaaS hosts in production).

### Client

```
cd client
npm install
npm run dev
```

Point it at the server via `client/.env.local`:

```
VITE_WS_URL=ws://localhost:8765
```

### Tests

```
source venv/bin/activate
pytest
```

`tests/test_integration_live_server.py` spins up a real server and drives
it over an actual socket; everything else tests `game_logic`/`rooms`
directly, with no networking involved. The daily challenge is covered by
`test_daily.py` (deterministic ordering), `test_solo_room.py` (the state
machine, driven with an explicit `now`), `test_solo_protocol.py` (including
that no queued/reserve card data or unrevealed card fields reach the client)
and `test_solo_handler.py` (fake-connection round trips).

The client has no test runner; check it with `cd client && npm run build`
(type-check + production build) and `npm run lint`.

## Decks

`general.json`, `rock.json`, and `pop.json` (repo root) are the actual
playable decks — Card-shaped JSON with title/artist/year/preview
URL/album art, resolved from the curated `*_deck_seed.json` files via
`build_general_deck.py` against the iTunes Search API (free, no key, but
unofficial/undocumented — see the script's own docstring). A theme is
only offered to players once its JSON file actually exists on disk (see
`server/deck/loader.py`'s `available_themes`); to add a new playlist,
create `<name>_seed.json`, point `build_general_deck.py`'s `SEED_FILE`/
`OUTPUT_FILE` at it, run it, and make sure the Dockerfile copies the
result into the image.

## Deploying

The `Dockerfile` builds the server only (the client is a separate static
build/deploy). It copies `server/`, `general.json`, `rock.json`, and
`pop.json` into the image — any new deck file needs the same treatment.
