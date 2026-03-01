# Split Panes + Work Board Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-agent split panes to the dashboard and a shared MCP work board so agents can see each other's claimed tasks and avoid duplicating effort.

**Architecture:** The existing FastAPI app (port 8400) gains a mounted FastMCP sub-app at `/mcp` exposing three tools (`claim_task`, `release_task`, `read_board`). Work board state is an in-memory dict broadcast over the existing WebSocket. The dashboard UI gains dynamic per-session panes and a Work Board panel in the sidebar.

**Tech Stack:** Python 3.9+, FastAPI, FastMCP (`mcp` package), vanilla JS, CSS flexbox

---

## Task 1: Add `mcp` package and work board state to server.py

**Files:**
- Modify: `requirements.txt`
- Modify: `server.py`

**Step 1: Add mcp to requirements**

Edit `requirements.txt` to:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
mcp>=1.0.0
```

**Step 2: Install**

```bash
pip install -r requirements.txt
```

Expected: installs without errors, `mcp` package available.

**Step 3: Add work board state and board broadcast to server.py**

After the existing `clients: set[WebSocket] = set()` line, add:

```python
work_board: dict[str, str] = {}


async def board_broadcast() -> None:
    payload = json.dumps({"type": "board_update", "board": work_board})
    dead: set[WebSocket] = set()
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)
```

**Step 4: Verify server still starts**

```bash
python server.py
```

Expected: `Uvicorn running on http://127.0.0.1:8400` with no import errors. Ctrl+C to stop.

**Step 5: Commit**

```bash
git add requirements.txt server.py
git commit -m "feat: add work board state and board broadcast to server"
```

---

## Task 2: Add MCP server with three tools

**Files:**
- Modify: `server.py`

**Step 1: Add FastMCP import at top of server.py**

Add to the imports block:
```python
from mcp.server.fastmcp import FastMCP
```

**Step 2: Create the MCP server and define tools**

Add this block after `board_broadcast()` and before the `@app.post("/event")` route:

```python
mcp_server = FastMCP("agent-dashboard-board")


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
```

**Step 3: Mount MCP app on FastAPI**

Add this line immediately after the `app = FastAPI(...)` line:

```python
app.mount("/mcp", mcp_server.streamable_http_app())
```

**Step 4: Verify MCP endpoint responds**

Start the server, then in another terminal:

```bash
python server.py
```

```bash
curl -s http://localhost:8400/mcp
```

Expected: JSON response (may be an MCP protocol envelope or empty 200 — not a 404).

**Step 5: Test claim_task via curl**

```bash
curl -s -X POST http://localhost:8400/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"claim_task","arguments":{"session_id":"test123","task":"refactor auth module"}}}'
```

Expected: JSON response containing `"ok"`.

**Step 6: Test read_board returns the claim**

```bash
curl -s -X POST http://localhost:8400/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_board","arguments":{}}}'
```

Expected: response contains `{"session_id":"test123","task":"refactor auth module"}`.

**Step 7: Commit**

```bash
git add server.py
git commit -m "feat: add MCP work board server with claim/release/read tools"
```

---

## Task 3: Update WebSocket replay and message routing in dashboard.html

**Files:**
- Modify: `dashboard.html`

The WebSocket currently receives raw event objects. After this task it will also receive `{"type": "board_update", "board": {...}}` messages. We need to route them.

**Step 1: Update the WebSocket onmessage handler**

Find this block in the `<script>` section:

```javascript
  ws.onmessage = (msg) => {
    try { ingest(JSON.parse(msg.data)); } catch {}
  };
```

Replace with:

```javascript
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type === 'board_update') {
        renderWorkBoard(data.board);
      } else {
        ingest(data);
      }
    } catch {}
  };
```

**Step 2: Add renderWorkBoard stub**

Add this function just before the `connect()` call:

```javascript
function renderWorkBoard(board) {
  const el = document.getElementById('workBoard');
  if (!el) return;
  el.innerHTML = '';
  const entries = Object.entries(board);
  if (entries.length === 0) {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:13px">No active claims</div>';
    return;
  }
  entries.forEach(([sid, task]) => {
    const item = document.createElement('div');
    item.className = 'board-item';
    item.innerHTML =
      `<div class="board-sid">${sid.slice(0, 10)}</div>` +
      `<div class="board-task">${task}</div>`;
    el.appendChild(item);
  });
}
```

**Step 3: Verify no console errors**

Open http://localhost:8400, open browser devtools Console. Hard refresh. Expected: no errors.

**Step 4: Commit**

```bash
git add dashboard.html
git commit -m "feat: route board_update WebSocket messages to renderWorkBoard"
```

---

## Task 4: Add Work Board panel to sidebar HTML and CSS

**Files:**
- Modify: `dashboard.html`

**Step 1: Add Work Board section to sidebar HTML**

Find the sidebar `<div class="sidebar">` in the HTML. Add this as the first child (before the "Event Rate" section):

```html
<div class="side-section">
  <div class="side-label">Work Board</div>
  <div id="workBoard">
    <div style="color:var(--text-dim);font-size:13px">No active claims</div>
  </div>
</div>
```

**Step 2: Add board-item CSS**

Add after the `.tool-tag:hover` rule:

```css
.board-item {
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}

.board-item:last-child { border-bottom: none; }

.board-sid {
  font-size: 10px;
  color: var(--amber);
  letter-spacing: .08em;
  margin-bottom: 2px;
}

.board-task {
  font-size: 12.5px;
  color: var(--text-hi);
  line-height: 1.4;
}
```

**Step 3: Verify Work Board section appears**

Open http://localhost:8400. Expected: "Work Board" section visible at the top of the sidebar with "No active claims" text.

**Step 4: Test live update**

With the server running and dashboard open, run:

```bash
curl -s -X POST http://localhost:8400/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"claim_task","arguments":{"session_id":"demo-session","task":"writing unit tests for payments module"}}}'
```

Expected: Work Board in the dashboard updates live to show the claim.

**Step 5: Commit**

```bash
git add dashboard.html
git commit -m "feat: add live Work Board panel to sidebar"
```

---

## Task 5: Add per-session panes to the event log

**Files:**
- Modify: `dashboard.html`

This is the largest change. The single log body becomes N side-by-side agent panes.

**Step 1: Add session pane state to the JS state object**

Find the `const state = {` block. Add `panes: {}` to it:

```javascript
const state = {
  events: [],
  filter: 'all',
  paused: false,
  panes: {},            // session_id → { el, lastSeen }
  stats: { total: 0, pre: 0, post: 0, stop: 0, notify: 0, sub: 0 },
  sessions: {},
  tools: {},
  rateBucket: [],
};
```

**Step 2: Replace the log-pane inner HTML structure**

Find the existing `.log-header` and `.log-body` in the HTML:

```html
<div class="log-pane">
    <div class="log-header">
      <span>TIME</span>
      <span>TYPE</span>
      <span>DETAIL</span>
    </div>
    <div class="log-body" id="logBody">
      <div class="empty-state" id="emptyState">
        ...
      </div>
    </div>
  </div>
```

Replace with:

```html
<div class="log-pane">
  <div class="pane-tabs" id="paneTabs">
    <button class="pane-tab active" data-session="all">All</button>
  </div>
  <div class="panes-area" id="panesArea">
    <!-- All-combined pane (current behaviour) -->
    <div class="agent-pane" id="pane-all" data-session="all">
      <div class="log-header">
        <span>TIME</span><span>TYPE</span><span>DETAIL</span>
      </div>
      <div class="log-body" id="logBody">
        <div class="empty-state" id="emptyState">
          <div class="empty-icon">◈</div>
          <div>Waiting for hook events&hellip;</div>
          <div style="color:var(--text-dim);font-size:11px;letter-spacing:.08em">START SERVER · ADD HOOKS · WATCH AGENTS</div>
        </div>
      </div>
    </div>
    <!-- Per-session panes injected here by JS -->
  </div>
</div>
```

**Step 3: Add CSS for pane tabs and pane layout**

Add after the `.log-body::-webkit-scrollbar-thumb` rule:

```css
.pane-tabs {
  display: flex;
  gap: 1px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-mid);
  overflow-x: auto;
  flex-shrink: 0;
}

.pane-tabs::-webkit-scrollbar { height: 2px; }
.pane-tabs::-webkit-scrollbar-thumb { background: var(--border-hi); }

.pane-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: .06em;
  padding: 6px 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}

.pane-tab:hover { color: var(--text-hi); }

.pane-tab.active {
  color: var(--amber-hi);
  border-bottom-color: var(--amber);
}

.panes-area {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.agent-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  min-width: 0;
}

.agent-pane:last-child { border-right: none; }

.agent-pane.hidden { display: none; }

.pane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}

.pane-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}

.pane-dot.active {
  background: var(--green);
  box-shadow: 0 0 5px var(--green);
  animation: pulse-dot 2s ease-in-out infinite;
}
```

**Step 4: Add getOrCreatePane function to JS**

Add this function before the `ingest()` function:

```javascript
function getOrCreatePane(sessionId) {
  if (state.panes[sessionId]) return state.panes[sessionId];

  // Create pane element
  const pane = document.createElement('div');
  pane.className = 'agent-pane hidden';
  pane.dataset.session = sessionId;
  pane.innerHTML =
    `<div class="pane-header">` +
      `<div class="pane-dot" id="dot-${sessionId}"></div>` +
      `<span>${sessionId.slice(0, 12)}</span>` +
    `</div>` +
    `<div class="log-header"><span>TIME</span><span>TYPE</span><span>DETAIL</span></div>` +
    `<div class="log-body" id="body-${sessionId}"></div>`;

  document.getElementById('panesArea').appendChild(pane);

  // Create tab
  const tab = document.createElement('button');
  tab.className = 'pane-tab';
  tab.dataset.session = sessionId;
  tab.textContent = sessionId.slice(0, 8);
  tab.addEventListener('click', () => switchTab(sessionId));
  document.getElementById('paneTabs').appendChild(tab);

  state.panes[sessionId] = { pane, lastSeen: 0 };
  return state.panes[sessionId];
}

function switchTab(sessionId) {
  // Update tab highlights
  document.querySelectorAll('.pane-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.session === sessionId)
  );

  if (sessionId === 'all') {
    // Show all panes side by side
    document.querySelectorAll('.agent-pane').forEach(p => p.classList.remove('hidden'));
  } else {
    // Show only the selected pane
    document.querySelectorAll('.agent-pane').forEach(p =>
      p.classList.toggle('hidden', p.dataset.session !== sessionId)
    );
  }
}

// Wire up the All tab
document.getElementById('paneTabs').addEventListener('click', (e) => {
  const tab = e.target.closest('.pane-tab');
  if (tab) switchTab(tab.dataset.session);
});
```

**Step 5: Update ingest() to also append to the per-session pane**

Find the `ingest(ev)` function. After the `appendEvent(ev)` call, add:

```javascript
  // Also append to per-session pane
  const sid = ev.session_id;
  if (sid) {
    const { pane } = getOrCreatePane(sid);
    const body = document.getElementById(`body-${sid}`);
    if (body && typeMatchesFilter(type, state.filter)) {
      const row = createRow(ev);
      body.appendChild(row);
      // Auto-scroll pane if not paused
      if (!state.paused) row.scrollIntoView({ block: 'end', behavior: 'auto' });
    }
    // Update activity dot
    state.panes[sid].lastSeen = Date.now();
    const dot = document.getElementById(`dot-${sid}`);
    if (dot) {
      dot.classList.add('active');
      clearTimeout(dot._timer);
      dot._timer = setTimeout(() => dot.classList.remove('active'), 10000);
    }
  }
```

**Step 6: Update clear button to also clear pane bodies**

Find the clear button event listener. Add pane clearing:

```javascript
  Object.keys(state.panes).forEach(sid => {
    const body = document.getElementById(`body-${sid}`);
    if (body) body.innerHTML = '';
  });
```

**Step 7: Verify panes appear with live data**

Open http://localhost:8400. Send a test event with a session_id:

```bash
curl -s -X POST http://localhost:8400/event \
  -H "Content-Type: application/json" \
  -d '{"hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/src/app.ts"},"session_id":"agent-alpha","ts":0}'
```

Expected:
- A new tab "agent-al" appears in the tab bar
- Clicking it shows only that agent's events
- Clicking "All" shows the combined stream

Send a second event with a different session_id and verify a second tab appears.

**Step 8: Commit**

```bash
git add dashboard.html
git commit -m "feat: split panes with per-session tabs and activity dots"
```

---

## Task 6: Update example config and README

**Files:**
- Modify: `example-hooks.json`
- Modify: `README.md`

**Step 1: Add mcpServers block to example-hooks.json**

Append to the root object in `example-hooks.json`:

```json
{
  "hooks": { "...existing..." },
  "mcpServers": {
    "agent-dashboard": {
      "type": "http",
      "url": "http://localhost:8400/mcp"
    }
  }
}
```

**Step 2: Add Work Board section to README**

Add a new `## Work Board (Agent Coordination)` section after the existing Setup section:

```markdown
## Work Board (Agent Coordination)

Sub-agents can coordinate via a shared work board to avoid duplicating effort.

### 1. Add the MCP server to your project

In your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "agent-dashboard": {
      "type": "http",
      "url": "http://localhost:8400/mcp"
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
```

**Step 3: Commit and push**

```bash
git add example-hooks.json README.md
git commit -m "docs: add MCP work board setup to README and example config"
git push
```

---

## Done

The dashboard now has:
- Per-agent panes with activity dots and a tab bar
- "All" tab restoring the combined stream
- Live Work Board in the sidebar
- MCP endpoint at `/mcp` for agent coordination

To coordinate agents, add the MCP config to any project and instruct agents to call `read_board` before starting and `claim_task` when they begin.
