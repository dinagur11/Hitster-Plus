"""Loads a theme's deck into list[Card].

Minimal version, built to unblock start_game (TimelineRoom had no way to
get any cards at all before this). Bridges to the existing root-level
general.json — built by build_general_deck.py via the iTunes Search API —
rather than CLAUDE.md's deck/themes/*.json convention; reorganizing that
build script's own output path is a separate follow-up, not done here, to
avoid two copies of the deck drifting out of sync.

Field names differ from Card's and get remapped: track_id -> deezer_id
(these are actually iTunes track ids, not Deezer ids — Card's field is
named for the originally-planned Deezer source; renaming that model field
is out of scope here too), year -> release_year.
"""

import json
from pathlib import Path

from server.models.card import Card

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GENERAL_DECK_PATH = _REPO_ROOT / "general.json"
_ROCK_DECK_PATH = _REPO_ROOT / "rock.json"
_POP_DECK_PATH = _REPO_ROOT / "pop.json"

_KNOWN_THEMES = {
    "general": _GENERAL_DECK_PATH,
    "rock": _ROCK_DECK_PATH,
    "pop": _POP_DECK_PATH,
}


def available_themes() -> list[str]:
    """Theme names whose backing JSON file actually exists on disk right
    now, sorted. `_KNOWN_THEMES` is the full registry of theme->path
    mappings this module knows how to build a deck for; a theme only
    becomes real once its file is actually built (build_general_deck.py)
    and present — e.g. a themed deck seed added to the repo but not yet
    resolved via the iTunes API shouldn't be offered as playable. Checked
    fresh on every call (not cached at import) so a file that appears or
    disappears takes effect without a server restart — callers needing a
    stable snapshot should call this once and reuse the result rather than
    calling it repeatedly within one action.
    """
    return sorted(name for name, path in _KNOWN_THEMES.items() if path.is_file())


def load_theme(theme: str = "general") -> list[Card]:
    """Return a fresh list[Card] for `theme`. Raises ValueError for an
    unrecognized theme name, or one whose file isn't actually present yet
    (see available_themes) — never lets a missing file surface as a raw
    FileNotFoundError."""
    path = _KNOWN_THEMES.get(theme)
    if path is None or not path.is_file():
        raise ValueError(f"unknown deck theme {theme!r} — available themes: {available_themes()}")

    raw_entries = json.loads(path.read_text())
    return [
        Card(
            deezer_id=int(entry["track_id"]),
            title=entry["title"],
            artist=entry["artist"],
            release_year=entry["year"],
            preview_url=entry["preview_url"],
            album_art_url=entry["album_art_url"],
        )
        for entry in raw_entries
    ]
