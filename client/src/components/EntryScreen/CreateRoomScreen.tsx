import { useEffect, useState } from "react";
import "./EntryScreen.css";

/** Display metadata for every theme the server could ever offer — a
 * superset, not the source of truth for what's actually playable right
 * now. `availableThemes` (from the server's list_themes reply) says which
 * of these are real; a theme missing from that list (its deck file hasn't
 * been built yet — see server/deck/loader.py's available_themes) is never
 * shown, even if it has an entry here. "general" plays the full deck at
 * the standard 10-card win length; every other playlist is a smaller deck
 * capped at 5 (see server/rooms/room_manager.py's create_room). */
const PLAYLIST_INFO: Record<string, { label: string; hint: string }> = {
  general: { label: "General", hint: "Full deck · first to 10 wins" },
  rock: { label: "Rock", hint: "Rock deck · first to 5 wins" },
  pop: { label: "Pop", hint: "Pop deck · first to 5 wins" },
};

function describeTheme(theme: string): { label: string; hint: string } {
  return PLAYLIST_INFO[theme] ?? { label: theme, hint: "First to 5 wins" };
}

// Stable reference (not a fresh literal on every render) so the
// availableThemes-omitted fallback doesn't make the effect below think
// the list changed on every render.
const DEFAULT_THEMES = ["general"];

interface CreateRoomScreenProps {
  onCreate: (displayName: string, theme: string) => void;
  /** Which playlists the server confirmed it can actually start a room
   * with right now (its list_themes reply) — null while that reply
   * hasn't arrived yet, which renders as a loading state rather than a
   * guessed list. Omitted entirely (the fixture-only dev harness, which
   * doesn't wire a live socket) falls back to just "general". */
  availableThemes?: string[] | null;
  /** Omit to hide the "join a room instead" link — the fixture-only
   * standalone views (App.tsx's dev harness) don't wire this. */
  onSwitchToJoin?: () => void;
  /** Wordmark click -> home. Omitted renders the wordmark as plain text. */
  onWordmarkClick?: () => void;
}

/** Create-room flow: enter a display name, pick a playlist, get a room
 * code back, land in the lobby as host. The room code itself is generated
 * wherever this hooks up to RoomManager.create_room — not here. */
export function CreateRoomScreen({
  onCreate,
  onSwitchToJoin,
  onWordmarkClick,
  availableThemes: availableThemesProp,
}: CreateRoomScreenProps) {
  const availableThemes = availableThemesProp === undefined ? DEFAULT_THEMES : availableThemesProp;
  const [name, setName] = useState("");
  const [theme, setTheme] = useState("general");

  // Once the real list arrives (or changes), make sure the selection is
  // actually one of the offered playlists — defaults to "general" when
  // it's available, otherwise whatever the list does have.
  useEffect(() => {
    if (availableThemes === null) return;
    if (availableThemes.includes(theme)) return;
    setTheme(availableThemes.includes("general") ? "general" : (availableThemes[0] ?? "general"));
  }, [availableThemes, theme]);

  const loading = availableThemes === null;

  return (
    <div className="entry-screen">
      <div className="entry-screen__card">
        {onWordmarkClick ? (
          <button type="button" className="entry-screen__title entry-screen__title--link" onClick={onWordmarkClick}>
            Hitster+
          </button>
        ) : (
          <h1 className="entry-screen__title">Hitster+</h1>
        )}
        <p className="entry-screen__subtitle">Create a room</p>

        <label className="entry-screen__field">
          <span className="entry-screen__field-label">Display name</span>
          <input
            type="text"
            className="entry-screen__input"
            placeholder="Your name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>

        <div className="entry-screen__field">
          <span className="entry-screen__field-label">Playlist</span>
          {loading ? (
            <p className="entry-screen__playlist-loading">Loading playlists…</p>
          ) : (
            <div className="entry-screen__playlist-options" role="radiogroup" aria-label="Playlist">
              {availableThemes.map((value) => {
                const info = describeTheme(value);
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={theme === value}
                    className={`entry-screen__playlist-option${
                      theme === value ? " entry-screen__playlist-option--selected" : ""
                    }`}
                    onClick={() => setTheme(value)}
                  >
                    <span className="entry-screen__playlist-name">{info.label}</span>
                    <span className="entry-screen__playlist-hint">{info.hint}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <button
          type="button"
          className="entry-screen__submit"
          disabled={!name.trim() || loading}
          onClick={() => onCreate(name.trim(), theme)}
        >
          Create room
        </button>
      </div>

      {onSwitchToJoin && (
        <button type="button" className="entry-screen__switch" onClick={onSwitchToJoin}>
          join a room instead
        </button>
      )}
    </div>
  );
}
