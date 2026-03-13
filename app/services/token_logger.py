"""Tracks token usage and prompt/response logs grouped by user question session.

Sessions are persisted to a JSON file so they survive container restarts.
"""

import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

DATA_FILE = os.environ.get("SESSION_LOG_PATH", "/app/data/sessions.json")

_stats: dict = defaultdict(lambda: {
    "requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
})

_sessions: list = []
_sessions_by_id: dict = {}


# ── Persistence ──────────────────────────────────────────────

def _load() -> None:
    """Load sessions from disk into memory on startup."""
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r") as f:
            saved = json.load(f)
        for session in saved:
            _sessions.append(session)
            _sessions_by_id[session["id"]] = session
            # Rebuild stats from loaded sessions
            for stage in session.get("stages", []):
                model = stage["model"]
                _stats[model]["requests"] += 1
                _stats[model]["total_input_tokens"] += stage["input_tokens"]
                _stats[model]["total_output_tokens"] += stage["output_tokens"]
    except (json.JSONDecodeError, KeyError):
        pass  # Corrupt file — start fresh


def _save() -> None:
    """Atomically write all sessions to disk."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_sessions, f, indent=2)
    os.replace(tmp, DATA_FILE)


# Load on import
_load()


# ── Session management ───────────────────────────────────────

def start_session(question: str) -> str:
    """Create a new session for a user question. Returns the session ID."""
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "stages": [],
    }
    _sessions.append(session)
    _sessions_by_id[session_id] = session
    _save()
    return session_id


def record_search(session_id: str, keywords: list, matched_endpoints: list) -> None:
    """Store the keyword list and matched endpoints for a metadata search."""
    session = _sessions_by_id.get(session_id)
    if session is None:
        return
    session["search"] = {
        "keywords": keywords,
        "keyword_count": len(keywords),
        "matched_endpoints": matched_endpoints,
        "match_count": len(matched_endpoints),
    }
    _save()


def record_stage(
    session_id: str,
    stage: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    prompt: str,
    response: str,
) -> None:
    """Record a single model call as a named stage within a session."""
    _stats[model]["requests"] += 1
    _stats[model]["total_input_tokens"] += input_tokens
    _stats[model]["total_output_tokens"] += output_tokens

    session = _sessions_by_id.get(session_id)
    if session is None:
        return

    session["total_input_tokens"] += input_tokens
    session["total_output_tokens"] += output_tokens
    session["stages"].append({
        "stage": stage,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "prompt": prompt,
        "response": response,
    })
    _save()


# ── Accessors ────────────────────────────────────────────────

def get_stats() -> dict:
    """Return token usage totals per model."""
    return {model: dict(counts) for model, counts in _stats.items()}


def get_sessions() -> list:
    """Return all sessions in reverse-chronological order."""
    return list(reversed(_sessions))


def get_session(session_id: str) -> dict | None:
    """Return a single session by ID."""
    return _sessions_by_id.get(session_id)
