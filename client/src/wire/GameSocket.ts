import type { IncomingMessage, OutgoingMessage } from "./messages";

export type ConnectionStatus = "disconnected" | "connecting" | "open" | "closed";

const RECONNECT_TOKEN_STORAGE_KEY = "hitster.reconnectToken";
const RECONNECT_RETRY_DELAY_MS = 2000;

function getStoredReconnectToken(): string | null {
  try {
    return localStorage.getItem(RECONNECT_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeReconnectToken(token: string): void {
  try {
    localStorage.setItem(RECONNECT_TOKEN_STORAGE_KEY, token);
  } catch {
    // best-effort only — a failed write just means a refresh won't resume
  }
}

function clearStoredReconnectTokenImpl(): void {
  try {
    localStorage.removeItem(RECONNECT_TOKEN_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * Thin wrapper around the browser WebSocket: connect, send/receive JSON
 * messages matching the real wire contract (messages.ts), and reconnect-
 * token handling exactly as the server expects it.
 *
 * Reconnect-token behavior: every successful `joined` response's token is
 * persisted to localStorage (per ws_handler.py's own frontend-note: a
 * page refresh needs this to survive, not just JS memory). Every time a
 * connection opens — including the very first one, so a page reload
 * resumes an existing session automatically — if a token is stored, a
 * `reconnect` message is sent immediately, before the caller does anything
 * else. If the caller actually wants a fresh room instead (e.g. the lobby
 * screen offers "leave" or "start over"), call `clearStoredReconnectToken()`
 * first so the next connect() doesn't resume the old identity.
 *
 * Also retries the raw connection itself (fixed delay, no backoff yet —
 * fine for a single local dev server) if it drops unexpectedly, since
 * without that the token-based reconnect would never get a chance to fire.
 */
export class GameSocket {
  private readonly url: string;
  private ws: WebSocket | null = null;
  private status: ConnectionStatus = "disconnected";
  private readonly messageListeners = new Set<(message: IncomingMessage) => void>();
  private readonly statusListeners = new Set<(status: ConnectionStatus) => void>();
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByCaller = false;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.closedByCaller = false;
    this.setStatus("connecting");

    const ws = new WebSocket(this.url);
    this.ws = ws;

    // Every handler guards on `this.ws !== ws`: once connect() is called
    // again (a manual reconnect, or the retry loop), this closure's `ws` is
    // superseded but its event listeners are still attached to the old,
    // now-irrelevant WebSocket object — without this guard a late-firing
    // stale `onclose` could still flip status to "closed" or schedule a
    // second reconnect after a newer connection already took over.
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.setStatus("open");
      const token = getStoredReconnectToken();
      if (token) {
        this.send({ type: "reconnect", reconnect_token: token });
      }
    };

    ws.onmessage = (event) => {
      if (this.ws !== ws) return;
      let message: IncomingMessage;
      try {
        message = JSON.parse(event.data as string);
      } catch {
        console.error("GameSocket: received malformed (non-JSON) message", event.data);
        return;
      }

      if (message.type === "joined") {
        storeReconnectToken(message.reconnect_token);
      }

      for (const listener of this.messageListeners) listener(message);
    };

    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.setStatus("closed");
      if (!this.closedByCaller) this.scheduleReconnect();
    };
  }

  /** A deliberate disconnect — no auto-retry follows this one. */
  disconnect(): void {
    this.closedByCaller = true;
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.setStatus("disconnected");
  }

  send(message: OutgoingMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("GameSocket: tried to send while not connected", message);
      return;
    }
    this.ws.send(JSON.stringify(message));
  }

  subscribe(listener: (message: IncomingMessage) => void): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  subscribeStatus(listener: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  clearStoredReconnectToken(): void {
    clearStoredReconnectTokenImpl();
  }

  private scheduleReconnect(): void {
    if (this.retryTimer !== null) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, RECONNECT_RETRY_DELAY_MS);
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    for (const listener of this.statusListeners) listener(status);
  }
}
