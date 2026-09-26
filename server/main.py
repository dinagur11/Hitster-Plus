"""Thin entrypoint: starts the websockets.serve() loop."""

import asyncio
import os

import websockets

from server.rooms.room_manager import RoomManager
from server.ws_handler import WsHandler

HOST = "0.0.0.0"
# Railway (and similar PaaS hosts) inject PORT at runtime and expect the
# server to bind to it — falls back to the existing local dev port when
# it's unset, so `python -m server.main` still works unchanged locally.
PORT = int(os.environ.get("PORT", 8765))


async def main() -> None:
    room_manager = RoomManager()
    handler = WsHandler(room_manager)

    async with websockets.serve(handler.handle_connection, HOST, PORT):
        await asyncio.gather(
            handler.run_disconnect_sweep_loop(),
            asyncio.get_running_loop().create_future(),  # run forever
        )


if __name__ == "__main__":
    asyncio.run(main())
