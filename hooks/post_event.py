#!/usr/bin/env python3
"""
Claude Code hook script — reads event JSON from stdin, enriches with transcript
context, then POSTs to agent-dashboard.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SERVER_URL = "http://127.0.0.1:8400/event"

# Cache: session_id → first user message (agent purpose)
_purpose_cache: dict[str, str] = {}


def extract_text(content) -> str:
    """Pull plain text out of a message content field (string or block list)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", "").strip())
        return " ".join(parts)
    return ""


def get_agent_purpose(transcript_path: str, session_id: str) -> str:
    """Read the transcript and return the first user/human message as purpose."""
    if session_id in _purpose_cache:
        return _purpose_cache[session_id]

    try:
        path = Path(transcript_path)
        if not path.exists():
            return ""

        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = msg.get("role", "")
                if role in ("user", "human"):
                    text = extract_text(msg.get("content", ""))
                    # Skip very short system-ish lines
                    if len(text) > 10:
                        # Truncate long tasks
                        purpose = text[:200].replace("\n", " ")
                        _purpose_cache[session_id] = purpose
                        return purpose
    except Exception:
        pass

    return ""


def get_recent_thinking(transcript_path: str) -> str:
    """Return the last assistant text message to show what the agent was thinking."""
    try:
        path = Path(transcript_path)
        if not path.exists():
            return ""

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("role") == "assistant":
                text = extract_text(msg.get("content", ""))
                if len(text) > 10:
                    return text[:150].replace("\n", " ")
    except Exception:
        pass

    return ""


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        event = json.loads(raw)
        event["ts"] = time.time()

        # Enrich with transcript context
        transcript_path = event.get("transcript_path", "")
        session_id = event.get("session_id", "")

        if transcript_path and session_id:
            purpose = get_agent_purpose(transcript_path, session_id)
            if purpose:
                event["agent_purpose"] = purpose

            thinking = get_recent_thinking(transcript_path)
            if thinking:
                event["agent_thinking"] = thinking

        data = json.dumps(event).encode()
        req = urllib.request.Request(
            SERVER_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=1)

    except (urllib.error.URLError, ConnectionRefusedError):
        pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
