import type { Card } from "../types";

// Placeholder album art as an inline SVG data URI — no network dependency
// for dev/preview. Swap for real Deezer URLs once track_provider.py exists.
function art(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  const hue = hash % 360;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
    <rect width="200" height="200" fill="hsl(${hue} 35% 22%)" />
    <circle cx="100" cy="100" r="55" fill="hsl(${hue} 40% 14%)" />
    <circle cx="100" cy="100" r="10" fill="hsl(${hue} 35% 30%)" />
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const bohemianRhapsody: Card = {
  deezer_id: 1,
  title: "Bohemian Rhapsody",
  artist: "Queen",
  release_year: 1975,
  preview_url: "",
  album_art_url: art("bohemian-rhapsody"),
};

export const billieJean: Card = {
  deezer_id: 2,
  title: "Billie Jean",
  artist: "Michael Jackson",
  release_year: 1983,
  preview_url: "",
  album_art_url: art("billie-jean"),
};

export const smellsLikeTeenSpirit: Card = {
  deezer_id: 3,
  title: "Smells Like Teen Spirit",
  artist: "Nirvana",
  release_year: 1991,
  preview_url: "",
  album_art_url: art("teen-spirit"),
};

export const rollingInTheDeep: Card = {
  deezer_id: 4,
  title: "Rolling in the Deep",
  artist: "Adele",
  release_year: 2010,
  preview_url: "",
  album_art_url: art("rolling-deep"),
};

// The card currently being placed. Title/artist/year stay hidden in the UI
// until REVEAL — components only ever read release_year off this for
// snapping logic when explicitly told to (dev/test convenience), never to
// render it before a real reveal happens.
export const mysteryCardA: Card = {
  deezer_id: 5,
  title: "Hey Jude",
  artist: "The Beatles",
  release_year: 1968,
  preview_url: "",
  album_art_url: art("mystery-a"),
};

export const mysteryCardB: Card = {
  deezer_id: 6,
  title: "Uptown Funk",
  artist: "Mark Ronson ft. Bruno Mars",
  release_year: 2014,
  preview_url: "",
  album_art_url: art("mystery-b"),
};
