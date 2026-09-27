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

The search itself is per-storefront (the `country` param) — Apple's own
default is the US store, and plenty of non-English/regional catalogs
(Hebrew-language releases among them) simply aren't in it even though
they're in the artist's home-market store. An entry whose title or artist
contains Hebrew script is searched against the Israeli store (country=IL)
instead of the default; everything else keeps searching the default store
exactly as before, so this doesn't change matching/results for existing
English (or other Latin-script) seed entries at all.

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
from rapidfuzz import fuzz

SEED_FILE = Path(__file__).parent / "hebrew_seed.json"
OUTPUT_FILE = Path(__file__).parent / "hebrew.json"

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

# Hebrew (֐-׿) and Alphabetic Presentation Forms (יִ-ﭏ,
# a handful of Hebrew ligatures/presentation variants also seen in the
# wild) — either is enough to say "this entry needs the Israeli store."
HEBREW_RE = re.compile(r"[֐-׿יִ-ﭏ]")

# Storefront to search when neither the title nor the artist is in Latin
# script — the default (unset country param) storefront is Apple's US
# store, which plenty of non-US-market catalogs simply aren't in.
HEBREW_STOREFRONT = "IL"


def storefront_for(entry: dict) -> str | None:
    """None means "use iTunes' own default store" (unset country param) —
    exactly today's behavior for every non-Hebrew entry, so this changes
    nothing about how English (or other Latin-script) seed entries match."""
    if HEBREW_RE.search(entry["title"]) or HEBREW_RE.search(entry["artist"]):
        return HEBREW_STOREFRONT
    return None


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


def itunes_search(term: str, limit: int = 10, country: str | None = None) -> list[dict]:
    params = {"term": term, "media": "music", "entity": "song", "limit": limit}
    if country is not None:
        params["country"] = country
    resp = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])


TITLE_MATCH_THRESHOLD = 85
ARTIST_MATCH_THRESHOLD = 78


def _matching_results(results: list[dict], wanted_title_norm: str, wanted_artist_norm: str, fuzzy: bool) -> list[dict]:
    if fuzzy:
        # Real-world transliterated names (especially Hebrew -> Latin,
        # where there's no single canonical spelling: "HaTarnegolim" vs
        # iTunes' own "Hatarnegoolim", "Tamouz" vs "Tamuz") rarely come
        # back letter-for-letter identical to however the seed happened to
        # spell them. token_sort_ratio for the title tolerates word-order
        # differences. token_set_ratio (not partial_ratio) for the artist:
        # it tolerates iTunes crediting just the primary artist when the
        # seed included a featured one ("Noa Kirel feat. Shahar Saul" vs
        # iTunes' "Noa Kirel" scores 100, since every word in the shorter
        # name appears in the longer one) without partial_ratio's failure
        # mode on short names — partial_ratio scores "Netta" against the
        # unrelated "Elektro Vendetta" at ~89 purely because "netta" is a
        # character substring of "venDETTA", a false positive
        # token_set_ratio doesn't make (~48, correctly low) since it
        # compares whole word sets rather than raw character alignment.
        return [
            r for r in results
            if fuzz.token_sort_ratio(wanted_title_norm, normalize(r.get("trackName", ""))) >= TITLE_MATCH_THRESHOLD
            and fuzz.token_set_ratio(wanted_artist_norm, normalize(r.get("artistName", ""))) >= ARTIST_MATCH_THRESHOLD
        ]
    return [
        r for r in results
        if wanted_title_norm in normalize(r.get("trackName", ""))
        and wanted_artist_norm in normalize(r.get("artistName", ""))
    ]


def pick_best_result(results: list[dict], wanted_title: str, wanted_artist: str, fuzzy: bool = False) -> dict | None:
    """Among results matching the title/artist, prefer non-compilation
    entries, and among those, the earliest release date — that's the best
    available proxy for the original pressing without a second data source.

    `fuzzy=False` (the default) is the original exact-substring behavior,
    unchanged — every existing (English/Latin-script) seed entry that
    already resolved correctly keeps matching exactly the same candidates,
    ranked exactly the same way. `fuzzy=True` is strictly a fallback (see
    resolve_song): it's only ever tried after the exact-substring pass
    already came back empty, specifically so it can never change which
    candidate wins for anything that already worked — it can only turn a
    previous "no match" into a match.
    """
    wanted_title_norm = normalize(wanted_title)
    wanted_artist_norm = normalize(wanted_artist)

    matching = _matching_results(results, wanted_title_norm, wanted_artist_norm, fuzzy)
    if not matching:
        return None

    non_compilation = [r for r in matching if not looks_like_compilation(r)]
    candidates = non_compilation or matching  # fall back rather than skip the song

    def release_year(r: dict) -> int:
        date_str = r.get("releaseDate", "")
        return int(date_str[:4]) if date_str else 9999  # unknown dates sort last

    return min(candidates, key=release_year)


def _resolve_from_query(query: str, entry: dict, country: str | None) -> dict | None:
    """One search + match attempt: exact-substring first, fuzzy only if
    that finds nothing at all among these same results (see
    pick_best_result's docstring for why fuzzy never overrides an exact
    match). Returns None (not the raw results) if neither pass finds
    anything — the caller doesn't need to know which pass would-be-matched."""
    results = itunes_search(query, country=country)
    if not results:
        return None
    best = pick_best_result(results, entry["title"], entry["artist"])
    if best is None:
        best = pick_best_result(results, entry["title"], entry["artist"], fuzzy=True)
    return best


def resolve_song(entry: dict) -> tuple[dict | None, str | None]:
    """Returns (card, warning). card is None if unresolvable."""
    country = storefront_for(entry)
    best = _resolve_from_query(f'{entry["artist"]} {entry["title"]}', entry, country)

    # Combining a transliterated artist name with a Hebrew title in one
    # query sometimes returns nothing at all from iTunes' own search
    # ranking, even though either term alone would surface the song (seen
    # repeatedly in practice — a combined query returning zero results
    # where a title-only query for the exact same song returns several).
    # Only tried once the combined query has already fully failed (exact
    # and fuzzy both), so this never changes an already-working match either.
    if best is None:
        time.sleep(REQUEST_DELAY_SECONDS)
        best = _resolve_from_query(entry["title"], entry, country)

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