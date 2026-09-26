import { useCallback, useEffect, useRef, useState } from "react";
import { GameSocket, type ConnectionStatus } from "./GameSocket";
import type { IncomingMessage, OutgoingMessage } from "./messages";

/**
 * Minimal React binding over GameSocket: opens one connection for the
 * component's lifetime, exposes connection status and a `send` function.
 * Deliberately doesn't do message-history/reducer bookkeeping here — step
 * 2's screens subscribe directly (via the returned `subscribe`) and decide
 * their own state shape, since a lobby view and a game view need very
 * different slices of the same message stream.
 */
export function useGameSocket(url: string) {
  const socketRef = useRef<GameSocket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");

  if (socketRef.current === null) {
    socketRef.current = new GameSocket(url);
  }

  useEffect(() => {
    const socket = socketRef.current!;
    const unsubscribe = socket.subscribeStatus(setStatus);
    socket.connect();
    return () => {
      unsubscribe();
      socket.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- url isn't expected to change at runtime
  }, []);

  // Stable references (socketRef.current never changes identity across
  // this hook's lifetime) so consumers can safely put these in effect
  // dependency arrays without triggering needless resubscribes.
  const send = useCallback((message: OutgoingMessage): void => socketRef.current!.send(message), []);
  const subscribe = useCallback(
    (listener: (message: IncomingMessage) => void): (() => void) => socketRef.current!.subscribe(listener),
    [],
  );

  return { status, send, subscribe, socket: socketRef.current };
}
