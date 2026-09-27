import { useEffect, useState } from "react";
import { CreateRoomScreen } from "../components/EntryScreen/CreateRoomScreen";
import { JoinRoomScreen } from "../components/EntryScreen/JoinRoomScreen";
import { HomeScreen } from "../components/HomeScreen/HomeScreen";
import { HowToPlayScreen } from "../components/HowToPlayScreen/HowToPlayScreen";
import { LobbyScreen } from "../components/LobbyScreen/LobbyScreen";
import type { LobbyRoomView } from "../types";
import { WS_URL } from "./config";
import { LiveGameFlow } from "./LiveGameFlow";
import type { IncomingMessage, StateUpdateMessage } from "./messages";
import { useGameSocket } from "./useGameSocket";

function toLobbyView(message: StateUpdateMessage): LobbyRoomView {
  return {
    room_id: message.room_id,
    lifecycle: message.lifecycle,
    players: message.players,
  };
}

type Screen = "home" | "create" | "join" | "lobby" | "started" | "how-to-play";

/**
 * Home/create/join/roster/start_game wired to the real server. Once
 * lifecycle flips to in_progress, LiveGameFlow takes over the same socket
 * and drives the actual round loop (placement, steal window, hints,
 * switch-track, mashup, reveal).
 *
 * Every screen but Home links its wordmark back here via onWordmarkClick.
 * Leaving from create/join/lobby navigates home immediately — nothing is
 * at stake there yet. Leaving mid-game goes through LiveGameFlow's own
 * confirm-leave modal first; only once the player actually confirms does
 * LiveGameFlow call handleGoHome (passed through as onLeaveGame).
 */
export function LiveLobbyFlow() {
  const { status, send, subscribe, socket } = useGameSocket(WS_URL);
  const [screen, setScreen] = useState<Screen>("home");
  const [viewingPlayerId, setViewingPlayerId] = useState<string | null>(null);
  const [room, setRoom] = useState<LobbyRoomView | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shown once, on the home screen, right after the host kicks this
  // player out of a lobby — null the rest of the time. Separate from
  // `error` since it needs to survive the trip back to the home screen
  // (error is cleared/only shown on the create/join/lobby screens).
  const [kickedNotice, setKickedNotice] = useState<string | null>(null);
  // Null until the "themes" reply lands (requested on entering the create
  // screen) — CreateRoomScreen treats null as "still loading" and only
  // ever offers a playlist the server just confirmed it can actually play
  // (see server/deck/loader.py's available_themes).
  const [availableThemes, setAvailableThemes] = useState<string[] | null>(null);
  // The exact state_update that flips lifecycle to in_progress — captured
  // here and handed to LiveGameFlow as its seed, since LiveGameFlow's own
  // subscription only starts once it mounts (one render after this
  // message is already consumed), and no further state_update necessarily
  // follows soon enough to unstick it otherwise.
  const [gameStartMessage, setGameStartMessage] = useState<StateUpdateMessage | null>(null);

  useEffect(() => {
    return subscribe((message: IncomingMessage) => {
      switch (message.type) {
        case "joined":
          setViewingPlayerId(message.player_id);
          setError(null);
          setKickedNotice(null);
          break;
        case "reconnected":
          setViewingPlayerId(message.player_id);
          setError(null);
          setKickedNotice(null);
          break;
        case "kicked":
          // Deliberately not calling handleGoHome here: this effect only
          // ever subscribes once (its dependency array is just
          // [subscribe], a stable reference), so a closure over anything
          // that changes across renders — handleGoHome included, since
          // it's a plain function recreated every render — would stay
          // frozen at whatever it was on the very first render. `socket`
          // and the setState setters are stable refs, so those are safe
          // to use directly here; everything else is inlined instead.
          socket?.disconnect();
          socket?.clearStoredReconnectToken();
          setRoom(null);
          setViewingPlayerId(null);
          setError(null);
          setStarting(false);
          setGameStartMessage(null);
          setKickedNotice("You were removed from the lobby by the host.");
          setScreen("home");
          break;
        case "state_update":
          if (message.lifecycle === "lobby") {
            setRoom(toLobbyView(message));
            setScreen("lobby");
            setStarting(false);
          } else {
            setGameStartMessage(message);
            setScreen("started");
            setStarting(false);
          }
          break;
        case "error":
          setError(message.message);
          setStarting(false);
          break;
        case "themes":
          setAvailableThemes(message.themes);
          break;
        default:
          break;
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- socket is a stable ref (useGameSocket backs it with a useRef, never a new identity across renders), so it's safe to read here without retriggering this effect
  }, [subscribe]);

  const handleCreate = (displayName: string, theme: string) => {
    setError(null);
    send({ type: "create_room", player_name: displayName, theme });
  };

  const handleJoin = (displayName: string, roomCode: string) => {
    setError(null);
    send({ type: "join_room", room_code: roomCode, player_name: displayName });
  };

  const handleStart = () => {
    setError(null);
    setStarting(true);
    send({ type: "start_game" });
  };

  const handleKick = (playerId: string) => {
    setError(null);
    send({ type: "kick_player", player_id: playerId });
  };

  // The socket connects once on mount and stays open for reuse across
  // create/join/lobby/game — reconnecting here would just be wasted round
  // trips. Only reconnect if handleGoHome actually tore the connection
  // down (status left "open"/"connecting" behind).
  const ensureConnected = () => {
    if (status === "disconnected" || status === "closed") socket?.connect();
  };

  const handleEnterCreate = () => {
    ensureConnected();
    setAvailableThemes(null);
    setKickedNotice(null);
    setScreen("create");
  };

  // Fires list_themes once the socket is actually open, not right on
  // handleEnterCreate's click — ensureConnected's connect() is async, so a
  // send() issued immediately after it (e.g. right after handleGoHome had
  // torn the connection down) would silently no-op against a socket that
  // isn't OPEN yet (see GameSocket.send). Re-fires harmlessly if the
  // connection drops and comes back while still on the create screen.
  useEffect(() => {
    if (screen === "create" && status === "open") {
      send({ type: "list_themes" });
    }
  }, [screen, status, send]);

  const handleEnterJoin = () => {
    ensureConnected();
    setKickedNotice(null);
    setScreen("join");
  };

  // No socket/game state involved — just a static rules page, so entering
  // and leaving it never touches the connection.
  const handleEnterHowToPlay = () => setScreen("how-to-play");

  // Actually leaves whatever room/connection is currently active. From the
  // lobby specifically, sends leave_room first — removed outright
  // server-side (see RoomManager.leave_room) rather than just marked
  // disconnected, so this player doesn't linger as a reconnectable ghost
  // for PLAYER_DISCONNECT_GRACE_SECONDS (previously: leaving and rejoining
  // under the same name showed two rows for a full minute). Then closes
  // the socket regardless — the server's own disconnect handling would
  // otherwise take over anyway, but by then leave_room has already
  // detached this connection from the room, so that's a no-op.
  const handleGoHome = () => {
    if (screen === "lobby") send({ type: "leave_room" });
    socket?.disconnect();
    socket?.clearStoredReconnectToken();
    setRoom(null);
    setViewingPlayerId(null);
    setError(null);
    setStarting(false);
    setGameStartMessage(null);
    setScreen("home");
  };

  if (screen === "started" && viewingPlayerId && gameStartMessage) {
    return (
      <LiveGameFlow
        send={send}
        subscribe={subscribe}
        viewingPlayerId={viewingPlayerId}
        onLeaveGame={handleGoHome}
        initialMessage={gameStartMessage}
      />
    );
  }

  if (screen === "lobby" && room && viewingPlayerId) {
    return (
      <LobbyScreen
        room={room}
        viewingPlayerId={viewingPlayerId}
        onStart={handleStart}
        starting={starting}
        error={error}
        onKick={handleKick}
        onWordmarkClick={handleGoHome}
      />
    );
  }

  const statusBanner = status !== "open" && (
    <p style={{ padding: "0.5rem 1rem", color: "var(--text-muted)" }}>status: {status}</p>
  );
  const errorBanner = error && <p style={{ padding: "0 1rem", color: "var(--color-amber)" }}>{error}</p>;

  if (screen === "join") {
    return (
      <div>
        {statusBanner}
        {errorBanner}
        <JoinRoomScreen onJoin={handleJoin} onSwitchToCreate={handleEnterCreate} onWordmarkClick={handleGoHome} />
      </div>
    );
  }

  if (screen === "how-to-play") {
    return <HowToPlayScreen onBack={() => setScreen("home")} />;
  }

  if (screen === "create") {
    return (
      <div>
        {statusBanner}
        {errorBanner}
        <CreateRoomScreen
          onCreate={handleCreate}
          onSwitchToJoin={handleEnterJoin}
          onWordmarkClick={handleGoHome}
          availableThemes={availableThemes}
        />
      </div>
    );
  }

  return (
    <div>
      {kickedNotice && (
        <p style={{ padding: "0.5rem 1rem", textAlign: "center", color: "var(--color-amber)" }}>{kickedNotice}</p>
      )}
      <HomeScreen onCreateGame={handleEnterCreate} onJoinLobby={handleEnterJoin} onHowToPlay={handleEnterHowToPlay} />
    </div>
  );
}
