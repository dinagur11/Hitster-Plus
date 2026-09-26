import { useState } from "react";
import "./EntryScreen.css";

interface JoinRoomScreenProps {
  onJoin: (displayName: string, roomCode: string) => void;
  /** Omit to hide the "host a game instead" link — the fixture-only
   * standalone views (App.tsx's dev harness) don't wire this. */
  onSwitchToCreate?: () => void;
  /** Wordmark click -> home. Omitted renders the wordmark as plain text. */
  onWordmarkClick?: () => void;
}

/** Join-room flow: enter a display name + room code, land in the lobby as
 * a regular (non-host) player. */
export function JoinRoomScreen({ onJoin, onSwitchToCreate, onWordmarkClick }: JoinRoomScreenProps) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");

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
        <p className="entry-screen__subtitle">Join a room</p>

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

        <label className="entry-screen__field">
          <span className="entry-screen__field-label">Room code</span>
          <input
            type="text"
            className="entry-screen__input entry-screen__input--code"
            placeholder="ABCDE"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </label>

        <button
          type="button"
          className="entry-screen__submit"
          disabled={!name.trim() || !code.trim()}
          onClick={() => onJoin(name.trim(), code.trim().toUpperCase())}
        >
          Join room
        </button>
      </div>

      {onSwitchToCreate && (
        <button type="button" className="entry-screen__switch" onClick={onSwitchToCreate}>
          host a game instead
        </button>
      )}
    </div>
  );
}
