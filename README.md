# agent-dashboard

A lightweight real-time dashboard for monitoring Claude Code sub-agent activity via the native hooks system.

![Dashboard UI](https://raw.githubusercontent.com/absolutebica/agent-dashboard/main/screenshot.png)

## What it does

When Claude Code runs sub-agents in your project, agent-dashboard shows you:

- **Every tool call** in real time — file reads, writes, bash commands, searches
- **Human-readable summaries** — `grep foo src/` becomes `Search "foo" in src/`
- **Agent thinking** — the text the agent wrote before calling the tool
- **Agent purpose** — the task the agent was given (read from the session transcript)
- **Live stats** — event rate, counts by type, active sessions, recent tools

No keystroke injection. No wrapper processes. Just Claude Code's native hook system posting events to a local server.

## Architecture

```
Claude Code (your project)
    │  hook fires on every tool call
    ▼
hooks/post_event.py        ← reads stdin, enriches with transcript context, POSTs
    │
    ▼
server.py (port 8400)      ← FastAPI, keeps event buffer, broadcasts via WebSocket
    │
    ▼
dashboard.html             ← served at http://localhost:8400, live WebSocket client
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the server

**Windows:**
```bat
start.bat
```

**Mac / Linux:**
```bash
bash start.sh
```

The dashboard will be available at **http://localhost:8400**.

### 3. Add hooks to your project

Copy the relevant section from `example-hooks.json` into your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python C:/path/to/agent-dashboard/hooks/post_event.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python C:/path/to/agent-dashboard/hooks/post_event.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/path/to/agent-dashboard/hooks/post_event.py"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/path/to/agent-dashboard/hooks/post_event.py"
          }
        ]
      }
    ]
  }
}
```

Update the path to point at your local `agent-dashboard` directory.

### 4. Run Claude Code

Start Claude Code in your project as normal. Events will stream into the dashboard automatically.

## Work Board (Agent Coordination)

Sub-agents can claim tasks and check what others are doing to avoid duplicating work.

### 1. Add the MCP server to your project

In your project's `.claude/settings.json`:

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

### 2. Add coordination instructions to your agent prompts

> Before starting any task, call `read_board` to check what other agents are working on.
> Call `claim_task` with your `session_id` and a short task description when you begin.
> Call `release_task` when done.

### Available MCP tools

| Tool | Args | Description |
|-|-|-|
| `read_board` | — | Returns all active claims |
| `claim_task` | `session_id`, `task` | Register what you're working on |
| `release_task` | `session_id` | Clear your claim when done |

## Multiple Projects

If you run Claude Code in two separate projects simultaneously, each project appears as its own tab in the dashboard. Events from each project's agents are grouped under their project tab.

To pin a project name (instead of using the directory name), set the env var in your hook config:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": ".*",
      "hooks": [{
        "type": "command",
        "command": "AGENT_DASHBOARD_PROJECT=financial-app python /path/to/hooks/post_event.py"
      }]
    }]
  }
}
```

## Dashboard features

| Feature | Description |
|-|-|
| Filter tabs | Show All / Pre / Post / Stop / Notify events |
| Live clock | Current time in the header |
| Connection dot | Green = connected, Red = server offline |
| Clear | Wipe the event log and stats |
| Scroll pause | Log pauses when you scroll up, resumes at bottom |
| Event rate | Events per minute over the last 60 seconds |
| Sessions | Active session IDs and event counts |
| Recent tools | Most-used tools ranked by call count |

## Event types

| Badge | Colour | Meaning |
|-|-|-|
| PRE | Amber | Agent is about to call a tool |
| POST | Green | Tool call completed |
| STOP | Red | Agent session ended |
| SUBST | Purple | Sub-agent stopped |
| NOTIF | Cyan | Notification event |

## Requirements

- Python 3.9+
- Claude Code with hooks support
- `fastapi` and `uvicorn` (installed via `requirements.txt`)

## Notes

- The hook script fails silently if the dashboard server is not running — it will never interrupt your agent
- Agent purpose and thinking are read from the Claude Code session transcript (`transcript_path` in the hook payload). If the transcript is not accessible the event still appears, just without that context
- Events are kept in memory (last 500). Clearing the log or restarting the server resets the buffer
