"""Card model — pure data, no placement/steal/mashup rule logic."""

from dataclasses import dataclass


@dataclass
class Card:
    deezer_id: int
    title: str
    artist: str
    release_year: int
    preview_url: str
    album_art_url: str
