"""
agent-dashboard: lightweight Claude Code hooks observability server.

Accepts POST /event from hook scripts, broadcasts to WebSocket clients,
serves the dashboard UI.
"""

import json
import time
from collections import deque
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from mcp.server.fastmcp import FastMCP

PORT = 8400
MAX_EVENTS = 500

app = FastAPI(title="agent-dashboard")
event_buffer: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
clients: set[WebSocket] = set()
work_board: dict[str, Any] = {}


async def board_broadcast() -> None:
    payload = json.dumps({"type": "board_update", "board": work_board})
    dead: set[WebSocket] = set()
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


mcp_server = FastMCP("agent-dashboard-board")
app.mount("/mcp", mcp_server.streamable_http_app())


@mcp_server.tool()
async def claim_task(session_id: str, task: str) -> str:
    """Register what you are currently working on to coordinate with other agents.
    Call this before starting any significant task. Pass your session_id from
    the hook event payload."""
    work_board[session_id] = task
    await board_broadcast()
    return "ok"


@mcp_server.tool()
async def release_task(session_id: str) -> str:
    """Clear your task claim when you finish or abandon a task."""
    work_board.pop(session_id, None)
    await board_broadcast()
    return "ok"


@mcp_server.tool()
async def read_board() -> list[dict[str, str]]:
    """Return all currently claimed tasks so you can check before starting work.
    If another agent has already claimed what you planned to do, pick something else."""
    return [{"session_id": sid, "task": task} for sid, task in work_board.items()]


async def broadcast(event: dict[str, Any]) -> None:
    payload = json.dumps(event)
    dead: set[WebSocket] = set()
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


@app.post("/event")
async def ingest_event(request_data: dict[str, Any]) -> dict[str, str]:
    event = {**request_data, "ts": request_data.get("ts", time.time())}
    event_buffer.append(event)
    await broadcast(event)
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    # Replay buffer to new client
    for event in event_buffer:
        await ws.send_text(json.dumps(event))
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        clients.discard(ws)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard() -> HTMLResponse:
    html_path = Path(__file__).parent / "dashboard.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
