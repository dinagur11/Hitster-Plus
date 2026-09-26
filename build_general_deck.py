"""
Resolves general_deck_seed.json (title/artist/expected year/genre) into real
track data and writes deck/themes/general.json in the Card schema the game
server expects.

Single data source: Apple's iTunes Search API (itunes.apple.com/search).
One unauthenticated GET request per song returns title, artist, a 30-second
preview URL, album artwork, and a release date, all together.

No API key needed — it's a free, keyless, but UNOFFICIAL/undocumented
endpoint. It has worked reliably for years, but Apple could restrict or
change it without notice (the same thing happened to Spotify's preview_url
field), so don't be surprised if this needs revisiting down the line.

Like every streaming catalog API, its "releaseDate" field describes
whichever ALBUM ENTRY the track happens to be catalogued under — which can
be a remaster or reissue rather than the song's true original release.
The stored `year` is taken directly from iTunes' matched entry (not the
curated seed) on the reasoning that if the date differs meaningfully from
what's expected, it likely means the WRONG pressing/version got matched —
so a mismatch is a signal to go listen and check, not something to
silently paper over with the seed's historical year. Mismatches greater
than 2 years in either direction are flagged as warnings for manual review.

Usage:
    pip install requests
    python build_general_deck.py
"""

import json
import re
import time
import sys
from pathlib import Path

import requests

SEED_FILE = Path(__file__).parent / "rock_seed.json"
OUTPUT_FILE = Path(__file__).parent / "rock.json"

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
# Undocumented endpoint with an undocumented rate limit — this delay is a
# conservative buffer, not a value Apple publishes anywhere.
REQUEST_DELAY_SECONDS = 3.0

# Collection (album) names containing these are deprioritized — usually
# "Greatest Hits"/"Best Of"/karaoke-style compilations, which is exactly the
# kind of entry whose release date is NOT the song's original release year.
COMPILATION_HINTS = (
    "greatest hits", "best of", "anthology", "essential", "collection",
    "karaoke", "tribute", "made famous by", "cover version",
)


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\(.*?\)|\[.*?\]", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def looks_like_compilation(result: dict) -> bool:
    collection = result.get("collectionName", "").lower()
    return any(hint in collection for hint in COMPILATION_HINTS)


def upscale_artwork(url: str) -> str:
    # iTunes gives a 100x100 thumbnail by default; this substring swap is a
    # long-standing, widely-used trick to get the same artwork at 600x600.
    return url.replace("100x100bb", "600x600bb") if url else ""


def itunes_search(term: str, limit: int = 10) -> list[dict]:
    resp = requests.get(
        ITUNES_SEARCH_URL,
        params={"term": term, "media": "music", "entity": "song", "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def pick_best_result(results: list[dict], wanted_title: str, wanted_artist: str) -> dict | None:
    """Among results matching the title/artist, prefer non-compilation
    entries, and among those, the earliest release date — that's the best
    available proxy for the original pressing without a second data source."""
    wanted_title_norm = normalize(wanted_title)
    wanted_artist_norm = normalize(wanted_artist)

    matching = [
        r for r in results
        if wanted_title_norm in normalize(r.get("trackName", ""))
        and wanted_artist_norm in normalize(r.get("artistName", ""))
    ]
    if not matching:
        return None

    non_compilation = [r for r in matching if not looks_like_compilation(r)]
    candidates = non_compilation or matching  # fall back rather than skip the song

    def release_year(r: dict) -> int:
        date_str = r.get("releaseDate", "")
        return int(date_str[:4]) if date_str else 9999  # unknown dates sort last

    return min(candidates, key=release_year)


def resolve_song(entry: dict) -> tuple[dict | None, str | None]:
    """Returns (card, warning). card is None if unresolvable."""
    results = itunes_search(f'{entry["artist"]} {entry["title"]}')
    if not results:
        return None, None

    best = pick_best_result(results, entry["title"], entry["artist"])
    if best is None:
        return None, None

    if not best.get("previewUrl"):
        return None, None

    itunes_date = best.get("releaseDate", "")
    itunes_year = int(itunes_date[:4]) if itunes_date else None
    year = itunes_year if itunes_year is not None else entry["year"]

    warning = None
    if itunes_year is None:
        warning = "no release date returned by iTunes — used curated seed year, verify manually"
    elif abs(itunes_year - entry["year"]) > 2:
        warning = (
            f"iTunes year ({itunes_year}) differs from seed year "
            f"({entry['year']}) by more than 2 — likely matched a different "
            f"pressing/remaster/version than intended, listen and verify"
        )

    card = {
        "track_id": str(best["trackId"]),
        "title": best.get("trackName", entry["title"]),
        "artist": best.get("artistName", entry["artist"]),
        "year": year,  # from iTunes' matched entry, not the curated seed
        "album_art_url": upscale_artwork(best.get("artworkUrl100", "")),
        "preview_url": best.get("previewUrl", ""),
    }
    return card, warning


def main() -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    cards = []
    failures = []
    warnings = []

    for i, entry in enumerate(seed, start=1):
        label = f'{entry["title"]} — {entry["artist"]}'
        print(f"[{i}/{len(seed)}] Resolving: {label}", file=sys.stderr)

        try:
            card, warning = resolve_song(entry)
        except requests.RequestException as exc:
            print(f"  ! request failed: {exc}", file=sys.stderr)
            failures.append(label)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        if card is None:
            print("  ! no usable match found (no result, or no preview audio)", file=sys.stderr)
            failures.append(label)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        if warning:
            print(f"  ! {warning}", file=sys.stderr)
            warnings.append(f"{label}: {warning}")

        cards.append(card)
        time.sleep(REQUEST_DELAY_SECONDS)

    OUTPUT_FILE.write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote {len(cards)} cards to {OUTPUT_FILE}", file=sys.stderr)
    if warnings:
        print(f"\n{len(warnings)} possible wrong-match warning(s) to double-check:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} song(s) failed to resolve — add manually:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)


if __name__ == "__main__":
    main()