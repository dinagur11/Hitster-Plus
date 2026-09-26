import { useState } from "react";
import "./EntryScreen.css";

interface CreateRoomScreenProps {
  onCreate: (displayName: string) => void;
  /** Omit to hide the "join a room instead" link — the fixture-only
   * standalone views (App.tsx's dev harness) don't wire this. */
  onSwitchToJoin?: () => void;
  /** Wordmark click -> home. Omitted renders the wordmark as plain text. */
  onWordmarkClick?: () => void;
}

/** Create-room flow: enter a display name, get a room code back, land in
 * the lobby as host. The room code itself is generated wherever this hooks
 * up to RoomManager.create_room — not here. */
export function CreateRoomScreen({ onCreate, onSwitchToJoin, onWordmarkClick }: CreateRoomScreenProps) {
  const [name, setName] = useState("");

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

        <button
          type="button"
          className="entry-screen__submit"
          disabled={!name.trim()}
          onClick={() => onCreate(name.trim())}
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
