import { useEffect, useRef, useState } from "react";
import { ConfirmLeaveModal } from "../components/ConfirmLeaveModal/ConfirmLeaveModal";
import { SoloEndScreen } from "../components/SoloEndScreen/SoloEndScreen";
import { SoloGameScreen } from "../components/SoloGameScreen/SoloGameScreen";
import { SoloRevealOverlay } from "../components/SoloRevealOverlay/SoloRevealOverlay";
import type { ConnectionStatus } from "./GameSocket";
import type { IncomingMessage, OutgoingMessage, SoloRevealMessage, SoloStateMessage } from "./messages";

interface LiveSoloFlowProps {
  send: (message: OutgoingMessage) => void;
  subscribe: (listener: (message: IncomingMessage) => void) => () => void;
  status: ConnectionStatus;
  /** Back to the home screen. The socket stays open; the caller sends
   * solo_leave itself, so this is also safe to call when the run is over. */
  onExit: () => void;
}

/**
 * Drives solo runs off the shared socket: starts one once the connection is
 * open, renders SoloGameScreen / reveal overlay / end screen from the
 * server's solo_state + solo_reveal messages, and starts a fresh run (new
 * random deck) on "Play again".
 *
 * A solo run lives and dies with its connection (no reconnect), so if the
 * socket drops mid-run this shows that the run ended rather than waiting
 * on a server that has already forgotten it.
 */
export function LiveSoloFlow({ send, subscribe, status, onExit }: LiveSoloFlowProps) {
  const [state, setState] = useState<SoloStateMessage | null>(null);
  const [reveal, setReveal] = useState<SoloRevealMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lostConnection, setLostConnection] = useState(false);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  const startSentRef = useRef(false);
  const startedRef = useRef(false);
  const finishedRef = useRef(false);

  // Start exactly once, as soon as the socket is actually open (a send
  // before that silently no-ops — see GameSocket.send).
  useEffect(() => {
    if (status === "open" && !startSentRef.current) {
      startSentRef.current = true;
      send({ type: "solo_start" });
    }
  }, [status, send]);

  // The run lives on this connection only: losing it mid-run ends the run.
  useEffect(() => {
    if (startedRef.current && !finishedRef.current && status !== "open" && status !== "connecting") {
      setLostConnection(true);
    }
  }, [status]);

  useEffect(() => {
    return subscribe((message: IncomingMessage) => {
      switch (message.type) {
        case "solo_started":
          startedRef.current = true;
          break;
        case "solo_state":
          if (!startedRef.current) break;
          setState(message);
          // The server clears reveal_deadline when the reveal hold ends;
          // that's what dismisses the overlay (never a client timer).
          if (message.reveal_deadline === null) setReveal(null);
          if (message.lifecycle === "finished" && message.result !== null && !finishedRef.current) {
            finishedRef.current = true;
          }
          break;
        case "solo_reveal":
          setReveal(message);
          break;
        case "error":
          // A stale multiplayer reconnect token produces an unrelated error on connect.
          if (startedRef.current && !/reconnect token/i.test(message.message)) setError(message.message);
          break;
        default:
          break;
      }
    });
  }, [subscribe, send]);

  // The server replaces a finished run on solo_start, so this is all it takes.
  const handlePlayAgain = () => {
    setState(null);
    setReveal(null);
    setError(null);
    startedRef.current = false;
    finishedRef.current = false;
    send({ type: "solo_start" });
  };

  if (lostConnection) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
        <p>The connection dropped, so this run has ended.</p>
        <button type="button" onClick={onExit} style={{ marginTop: "1rem" }}>
          Back to home
        </button>
      </div>
    );
  }

  if (state === null) {
    return (
      <div style={{ padding: "2rem", color: "var(--text-muted)" }}>
        <p>{status === "open" ? "Starting your solo run…" : `Connecting (${status})…`}</p>
        <button type="button" onClick={onExit} style={{ marginTop: "1rem" }}>
          Back to home
        </button>
      </div>
    );
  }

  // The final reveal still plays out; the end screen takes over once the
  // server clears its deadline.
  if (state.lifecycle === "finished" && reveal === null) {
    return <SoloEndScreen state={state} onPlayAgain={handlePlayAgain} onHome={onExit} />;
  }

  return (
    <>
      {error && <p style={{ padding: "0.5rem 1.5rem", color: "var(--color-amber)", textAlign: "center" }}>{error}</p>}

      <SoloGameScreen
        key={state.turn_log.length}
        state={state}
        revealing={reveal !== null}
        onFinishTurn={(slotIndex, guessedArtist, guessedTitle) => {
          setError(null);
          send({ type: "solo_finish_turn", slot_index: slotIndex, guessed_artist: guessedArtist, guessed_title: guessedTitle });
        }}
        onUseHint={() => {
          setError(null);
          send({ type: "solo_use_hint" });
        }}
        onSwitchTrack={() => {
          setError(null);
          send({ type: "solo_switch_track" });
        }}
        onWordmarkClick={() => setShowLeaveConfirm(true)}
      />

      {reveal && <SoloRevealOverlay reveal={reveal} revealDeadline={state.reveal_deadline} />}

      {showLeaveConfirm && <ConfirmLeaveModal onConfirm={onExit} onCancel={() => setShowLeaveConfirm(false)} />}
    </>
  );
}
