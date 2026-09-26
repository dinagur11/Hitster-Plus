import { useState } from "react";
import { GameScreen } from "./components/GameScreen/GameScreen";
import { HomeScreen } from "./components/HomeScreen/HomeScreen";
import { LobbyScreen } from "./components/LobbyScreen/LobbyScreen";
import { CreateRoomScreen } from "./components/EntryScreen/CreateRoomScreen";
import { JoinRoomScreen } from "./components/EntryScreen/JoinRoomScreen";
import {
  mashupRoundActorId,
  mashupRoundState,
  normalRoundState,
  normalRoundViewerId,
  stealWindowSkippedState,
  stealWindowState,
  viewingPlayerId,
} from "./fixtures/gameState";
import { joinedLobby, readyToStartLobby, readyToStartViewingPlayerId } from "./fixtures/lobbyState";
import {
  mashupReveal,
  normalRevealCorrect,
  normalRevealDiscarded,
  normalRevealStolen,
} from "./fixtures/revealState";
import { RevealOverlay } from "./components/RevealOverlay/RevealOverlay";
import type { GameRoomView, LobbyRoomView, Player } from "./types";
import type { RevealMessage } from "./wire/messages";
import { LiveLobbyFlow } from "./wire/LiveLobbyFlow";

type View =
  | "home"
  | "create"
  | "join"
  | "lobby"
  | "game-normal"
  | "game-normal-viewer"
  | "game-mashup"
  | "game-mashup-actor"
  | "steal-window"
  | "steal-window-skipped"
  | "reveal-normal-correct"
  | "reveal-normal-stolen"
  | "reveal-normal-discarded"
  | "reveal-mashup"
  | "live-lobby";

/**
 * Dev harness only: switches between every screen built so far so each is
 * reachable without a server. No websocket wiring yet — see fixtures/.
 *
 * Create/Join actually build a LobbyRoomView from what you type (not a
 * canned fixture) and land you in it — Create makes you the sole host,
 * Join drops you into the same several-players fixture as a regular
 * player, appended under whatever name you entered. The "ready to start"
 * nav button jumps straight to that fixture for review, since it has no
 * natural entry form of its own.
 */
/** Dev-only wrapper: layers RevealOverlay over its underlying GameScreen and
 * lets "Continue" actually dismiss it, demonstrating that this is a local,
 * client-owned overlay rather than a server-held phase. */
function RevealFixture({
  room,
  reveal,
  actingPlayerId,
}: {
  room: GameRoomView;
  reveal: RevealMessage;
  actingPlayerId: string;
}) {
  const [dismissed, setDismissed] = useState(false);
  const actingPlayerTimeline = room.players.find((p) => p.player_id === actingPlayerId)?.timeline ?? [];
  return (
    <>
      <GameScreen room={room} viewingPlayerId={viewingPlayerId} />
      {!dismissed && (
        <RevealOverlay
          reveal={reveal}
          players={room.players}
          actingPlayerId={actingPlayerId}
          actingPlayerTimeline={actingPlayerTimeline}
          onDismiss={() => setDismissed(true)}
        />
      )}
    </>
  );
}

export default function App() {
  // Boots straight into the real, server-backed app — not the static "home"
  // fixture below (same visual, but Create/Join there build a fake local
  // room and Start Game is a no-op). The fixture-switcher strip above still
  // lets you jump to any static screen for visual review; this is just
  // which one loads first.
  const [view, setView] = useState<View>("live-lobby");
  const goHome = () => setView("home");
  const [activeLobby, setActiveLobby] = useState<{ room: LobbyRoomView; viewingPlayerId: string }>({
    room: readyToStartLobby,
    viewingPlayerId: readyToStartViewingPlayerId,
  });

  const handleCreate = (displayName: string) => {
    const host: Player = {
      player_id: "you",
      name: displayName,
      is_host: true,
      connected: true,
      tokens: 0,
      timeline: [],
      had_mashup_round: false,
      turns_taken: 0,
    };
    setActiveLobby({
      room: { room_id: "AB3KP", lifecycle: "lobby", players: [host] },
      viewingPlayerId: host.player_id,
    });
    setView("lobby");
  };

  const handleJoin = (displayName: string, roomCode: string) => {
    const you: Player = {
      player_id: "you",
      name: displayName,
      is_host: false,
      connected: true,
      tokens: 0,
      timeline: [],
      had_mashup_round: false,
      turns_taken: 0,
    };
    setActiveLobby({
      room: { ...joinedLobby, room_id: roomCode, players: [...joinedLobby.players, you] },
      viewingPlayerId: you.player_id,
    });
    setView("lobby");
  };

  return (
    <div>
      <div className="fixture-switcher">
        <button
          type="button"
          className={view === "home" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("home")}
        >
          Home
        </button>
        <button
          type="button"
          className={view === "create" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("create")}
        >
          Create room
        </button>
        <button
          type="button"
          className={view === "join" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("join")}
        >
          Join room
        </button>
        <button
          type="button"
          className="fixture-switcher__btn"
          onClick={() => {
            setActiveLobby({ room: readyToStartLobby, viewingPlayerId: readyToStartViewingPlayerId });
            setView("lobby");
          }}
        >
          Lobby: ready to start
        </button>
        <button
          type="button"
          className={view === "game-normal" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("game-normal")}
        >
          Normal round fixture
        </button>
        <button
          type="button"
          className={view === "game-normal-viewer" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("game-normal-viewer")}
        >
          Normal round (viewer)
        </button>
        <button
          type="button"
          className={view === "game-mashup" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("game-mashup")}
        >
          Mashup round fixture
        </button>
        <button
          type="button"
          className={view === "game-mashup-actor" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("game-mashup-actor")}
        >
          Mashup round (actor)
        </button>
        <button
          type="button"
          className={view === "steal-window" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("steal-window")}
        >
          Steal window
        </button>
        <button
          type="button"
          className={view === "steal-window-skipped" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("steal-window-skipped")}
        >
          Steal window (skipped)
        </button>
        <button
          type="button"
          className={view === "reveal-normal-correct" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("reveal-normal-correct")}
        >
          Reveal: correct
        </button>
        <button
          type="button"
          className={view === "reveal-normal-stolen" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("reveal-normal-stolen")}
        >
          Reveal: stolen
        </button>
        <button
          type="button"
          className={view === "reveal-normal-discarded" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("reveal-normal-discarded")}
        >
          Reveal: discarded
        </button>
        <button
          type="button"
          className={view === "reveal-mashup" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("reveal-mashup")}
        >
          Reveal: mashup
        </button>
        <button
          type="button"
          className={view === "live-lobby" ? "fixture-switcher__btn fixture-switcher__btn--active" : "fixture-switcher__btn"}
          onClick={() => setView("live-lobby")}
        >
          Live lobby (real server)
        </button>
      </div>

      {/* key forces a remount on view/fixture switch, so a screen's local
          demo state doesn't leak between fixtures. */}
      {view === "home" && <HomeScreen key="home" onCreateGame={() => setView("create")} onJoinLobby={() => setView("join")} />}
      {view === "create" && (
        <CreateRoomScreen key="create" onCreate={handleCreate} onSwitchToJoin={() => setView("join")} onWordmarkClick={goHome} />
      )}
      {view === "join" && (
        <JoinRoomScreen key="join" onJoin={handleJoin} onSwitchToCreate={() => setView("create")} onWordmarkClick={goHome} />
      )}
      {view === "lobby" && (
        <LobbyScreen
          key={activeLobby.room.room_id}
          room={activeLobby.room}
          viewingPlayerId={activeLobby.viewingPlayerId}
          onStart={() => {}}
          onWordmarkClick={goHome}
        />
      )}
      {view === "game-normal" && (
        <GameScreen key="game-normal" room={normalRoundState} viewingPlayerId={viewingPlayerId} onWordmarkClick={goHome} />
      )}
      {view === "game-normal-viewer" && (
        <GameScreen key="game-normal-viewer" room={normalRoundState} viewingPlayerId={normalRoundViewerId} onWordmarkClick={goHome} />
      )}
      {view === "game-mashup" && (
        <GameScreen key="game-mashup" room={mashupRoundState} viewingPlayerId={viewingPlayerId} onWordmarkClick={goHome} />
      )}
      {view === "game-mashup-actor" && (
        <GameScreen key="game-mashup-actor" room={mashupRoundState} viewingPlayerId={mashupRoundActorId} onWordmarkClick={goHome} />
      )}
      {view === "steal-window" && (
        <GameScreen key="steal-window" room={stealWindowState} viewingPlayerId={viewingPlayerId} onWordmarkClick={goHome} />
      )}
      {view === "steal-window-skipped" && (
        <GameScreen
          key="steal-window-skipped"
          room={stealWindowSkippedState}
          viewingPlayerId={viewingPlayerId}
          onWordmarkClick={goHome}
        />
      )}
      {view === "reveal-normal-correct" && (
        <RevealFixture key="reveal-normal-correct" room={normalRoundState} reveal={normalRevealCorrect} actingPlayerId="p1" />
      )}
      {view === "reveal-normal-stolen" && (
        <RevealFixture key="reveal-normal-stolen" room={normalRoundState} reveal={normalRevealStolen} actingPlayerId="p1" />
      )}
      {view === "reveal-normal-discarded" && (
        <RevealFixture key="reveal-normal-discarded" room={normalRoundState} reveal={normalRevealDiscarded} actingPlayerId="p1" />
      )}
      {view === "reveal-mashup" && (
        <RevealFixture key="reveal-mashup" room={mashupRoundState} reveal={mashupReveal} actingPlayerId="p2" />
      )}
      {view === "live-lobby" && <LiveLobbyFlow key="live-lobby" />}
    </div>
  );
}
