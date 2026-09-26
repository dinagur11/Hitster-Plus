"""Fuzzy artist/title guess matching for the guess bonus token.

Pure functions only — no networking/asyncio. Uses rapidfuzz (a new
dependency, not yet listed in CLAUDE.md's tech stack — flag to add it
there).

Normalization applied to both the player's guess and the card's actual
metadata before scoring:
    - lowercase
    - strip punctuation
    - strip parenthetical tags, e.g. "(feat. X)", "(Remastered 2011)"
    - strip a leading "the"/"a"/"an"

Artist and title get separate matching functions/thresholds so they can be
tuned independently later; both start at the same threshold (~85) for now.
"""

import re
import string

from rapidfuzz import fuzz

ARTIST_MATCH_THRESHOLD = 85
TITLE_MATCH_THRESHOLD = 85

_PARENTHETICAL_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+")
_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)


def normalize_guess_text(text: str) -> str:
    """Lowercase, strip punctuation/parenthetical tags/leading article."""
    text = _PARENTHETICAL_RE.sub("", text)
    text = text.lower()
    text = text.translate(_PUNCTUATION_TABLE)
    text = " ".join(text.split())
    text = _LEADING_ARTICLE_RE.sub("", text)
    return text.strip()


def is_artist_guess_correct(guess: str, actual: str) -> bool:
    """Fuzzy-match a player's artist guess against the card's actual artist."""
    score = fuzz.ratio(normalize_guess_text(guess), normalize_guess_text(actual))
    return score >= ARTIST_MATCH_THRESHOLD


def is_title_guess_correct(guess: str, actual: str) -> bool:
    """Fuzzy-match a player's title guess against the card's actual title.

    Uses token_sort_ratio rather than plain ratio since titles are more
    often multi-word and word order in a guess may not match exactly.
    """
    score = fuzz.token_sort_ratio(normalize_guess_text(guess), normalize_guess_text(actual))
    return score >= TITLE_MATCH_THRESHOLD


def is_guess_bonus_earned(
    guessed_artist: str,
    guessed_title: str,
    actual_artist: str,
    actual_title: str,
) -> bool:
    """Whether both artist and title guesses are correct — the bonus token condition."""
    return is_artist_guess_correct(guessed_artist, actual_artist) and is_title_guess_correct(
        guessed_title, actual_title
    )
