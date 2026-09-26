import type { LobbyRoomView, Player } from "../types";

/**
 * Pre-game players: empty timeline, 0 tokens, 0 turns taken — everyone
 * starts this way until start_game deals the first cards.
 */
function lobbyPlayer(player_id: string, name: string, is_host: boolean): Player {
  return {
    player_id,
    name,
    is_host,
    connected: true,
    tokens: 0,
    timeline: [],
    had_mashup_round: false,
    turns_taken: 0,
  };
}

// -- Fixture 1: an empty lobby — just you, as host, right after creating a room. --

const soloHost = lobbyPlayer("p1", "Alice", true);

export const soloHostLobby: LobbyRoomView = {
  room_id: "AB3KP",
  lifecycle: "lobby",
  players: [soloHost],
};

export const soloHostViewingPlayerId = soloHost.player_id;

// -- Fixture 2: a lobby with several players joined — you're a regular player. --

const joinedHost = lobbyPlayer("p1", "Alice", true);
const joinedYou = lobbyPlayer("p2", "Bob", false);
const joinedOther = lobbyPlayer("p3", "Carol", false);

export const joinedLobby: LobbyRoomView = {
  room_id: "PQR7X",
  lifecycle: "lobby",
  players: [joinedHost, joinedYou, joinedOther],
};

export const joinedViewingPlayerId = joinedYou.player_id;

// -- Fixture 3: the moment right before start — full room, you're the host. --

const readyHost = lobbyPlayer("p1", "Alice", true);

export const readyToStartLobby: LobbyRoomView = {
  room_id: "9F2LM",
  lifecycle: "lobby",
  players: [
    readyHost,
    lobbyPlayer("p2", "Bob", false),
    lobbyPlayer("p3", "Carol", false),
    lobbyPlayer("p4", "Dave", false),
  ],
};

export const readyToStartViewingPlayerId = readyHost.player_id;
