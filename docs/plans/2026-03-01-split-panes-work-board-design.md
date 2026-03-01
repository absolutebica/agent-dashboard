# Design: Split Panes + Agent Work Board

**Date:** 2026-03-01
**Status:** Approved

## Problem

The current dashboard shows all agent events in a single continuous stream. When multiple sub-agents run in parallel it's hard to follow individual agents, and there is no mechanism for agents to coordinate or avoid working on the same thing.

## Goals

1. Split the event log into per-agent panes so each agent's activity is visually isolated
2. Add a shared work board so agents can claim tasks and check what others are doing before starting

## Non-goals

- Full agent-to-agent messaging (out of scope, overlaps with agentchattr)
- Persistent storage (separate future concern)
- Authentication on MCP endpoints

---

## Architecture

### Split-pane UI

The event log area changes from a single column to N equal-width columns, one per `session_id`. A tab bar across the header lets the user switch between:

- **All** — combined stream (current behaviour)
- **Per-agent tabs** — one tab per session, shows only that agent's pane

In split view all panes are visible side by side and scroll independently. The existing sidebar (stats, sessions, recent tools) is retained on the right, with the Work Board added above it.

Each agent pane has a header showing a short session ID and an activity dot:
- Pulsing green = received an event in the last 10 seconds
- Dim = idle

### Work Board (MCP server on port 8401)

`server.py` gains a minimal MCP server (streamable-HTTP, `/mcp` endpoint) alongside the existing FastAPI app.

**Tools exposed:**

| Tool | Args | Returns | Description |
|-|-|-|-|
| `claim_task` | `task: str` | `ok` | Register what this agent is working on |
| `release_task` | — | `ok` | Clear this agent's claim |
| `read_board` | — | `list[{session, task}]` | Return all active claims |

The board is stored in-memory as `dict[session_id, task_description]`. On any board change the server broadcasts a `board_update` WebSocket message to all dashboard clients.

### Agent setup

Agents add the dashboard MCP to their project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "agent-dashboard": {
      "type": "http",
      "url": "http://localhost:8401/mcp"
    }
  }
}
```

Coordination is opt-in via prompt instructions:

> Before starting any task, call `read_board` to check what other agents are working on. Call `claim_task` when you begin and `release_task` when done.

---

## UI Layout

```
┌─ HEADER ─────────────────────────────────────────────────────────────────────┐
│ [All] [Agent-1] [Agent-2] [Agent-3]            CLEAR  ● LIVE   12:34:56     │
├──────────────────┬──────────────────┬──────────────────┬──────────────────────┤
│ AGENT-1 abc1234  │ AGENT-2 def4567  │ AGENT-3 ghi7890  │ WORK BOARD           │
│ ● active         │ ● active         │ ○ idle            │ abc1234              │
│ ─────────────    │ ─────────────    │ ─────────────     │   refactor auth mod  │
│ events...        │ events...        │ events...         │ def4567              │
│                  │                  │                   │   add unit tests     │
│                  │                  │                   │ ─────────────        │
│                  │                  │                   │ STATS / SESSIONS     │
│                  │                  │                   │ RECENT TOOLS         │
└──────────────────┴──────────────────┴──────────────────┴──────────────────────┘
```

---

## Data Flow

```
Agent calls claim_task("refactor auth")
  → POST /mcp  (port 8401)
  → board dict updated
  → server broadcasts board_update over WebSocket
  → dashboard Work Board panel re-renders

Agent hook fires (PreToolUse)
  → POST /event  (port 8400)
  → event buffer updated, session_id noted
  → server broadcasts event over WebSocket
  → correct agent pane appends row
  → agent tab/header activity dot goes green
```

---

## Implementation Tasks

1. Add MCP server to `server.py` (port 8401, three tools, board broadcast)
2. Update `dashboard.html` — tab bar, pane layout, per-pane event routing
3. Update sidebar — Work Board section above existing stats
4. Update `example-hooks.json` — add MCP server config example
5. Update README — document MCP setup and coordination prompt
