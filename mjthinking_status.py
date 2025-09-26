#!/usr/bin/env python3
"""Quick status dump for the latest MJThinking session."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show snapshot of the latest MJThinking session")
    parser.add_argument(
        "--session",
        help="Session ID or path (defaults to most recent)",
    )
    return parser.parse_args()


def resolve_session_dir(session_arg: Optional[str]) -> Path:
    if session_arg:
        candidate = Path(session_arg)
        if candidate.is_dir():
            return candidate
        candidate = RUNS_DIR / session_arg
        if candidate.is_dir():
            return candidate
        raise SystemExit(f"Session '{session_arg}' not found")

    if not RUNS_DIR.exists():
        raise SystemExit("runs/ directory does not exist yet. Launch a session first.")

    sessions = sorted(
        [p for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "session.jsonl").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not sessions:
        raise SystemExit("No sessions found.")
    return sessions[0]


def load_session_snapshot(session_dir: Path) -> dict:
    meta_path = session_dir / "session.jsonl"
    if not meta_path.exists():
        raise SystemExit(f"No session.jsonl in {session_dir}")

    snapshot: dict = {"session_id": session_dir.name, "status": "in_progress"}
    with meta_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("event")
            if kind == "session_start":
                snapshot.update(
                    question=event.get("question"),
                    chains=event.get("chains"),
                    start_timestamp=event.get("timestamp"),
                )
            elif kind == "round_complete":
                snapshot.update(
                    last_round=event.get("round"),
                    last_round_majority=f"{event.get('majority_count')} / {event.get('majority_total')}",
                    referee=event.get("referee_verdict"),
                    numeric=event.get("numeric_verdict"),
                    elapsed_seconds=event.get("elapsed_seconds"),
                    eta_seconds=event.get("eta_seconds"),
                )
            elif kind == "session_complete":
                snapshot.update(
                    status=event.get("status"),
                    final_answer=event.get("final_answer"),
                    referee=event.get("referee_verdict"),
                    numeric=event.get("numeric_verdict"),
                    elapsed_seconds=event.get("elapsed_seconds"),
                    eta_seconds=0,
                    completion_timestamp=event.get("timestamp"),
                )
    return snapshot


def format_duration(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "--"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return "".join(parts)


def render(snapshot: dict) -> str:
    lines = []
    lines.append("=== MJThinking Session Status ===")
    lines.append(f"Session ID      : {snapshot.get('session_id', '--')}")
    if snapshot.get("question"):
        lines.append(f"Question        : {snapshot['question']}")
    if snapshot.get("chains") is not None:
        lines.append(f"Initial chains  : {snapshot['chains']}")
    lines.append(f"Status          : {snapshot.get('status', '--')}")
    if snapshot.get("last_round") is not None:
        lines.append(f"Last round      : {snapshot['last_round']}")
    if snapshot.get("last_round_majority"):
        lines.append(f"Majority        : {snapshot['last_round_majority']}")
    if snapshot.get("referee"):
        lines.append(f"Referee verdict : {snapshot['referee']}")
    if snapshot.get("numeric"):
        lines.append(f"Numeric check   : {snapshot['numeric']}")
    if snapshot.get("elapsed_seconds") is not None:
        lines.append(f"Elapsed         : {format_duration(snapshot['elapsed_seconds'])}")
    if snapshot.get("eta_seconds") not in (None, 0):
        lines.append(f"ETA             : {format_duration(snapshot['eta_seconds'])}")
    if snapshot.get("final_answer"):
        lines.append("Final answer:")
        lines.append(snapshot['final_answer'])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(args.session)
    snapshot = load_session_snapshot(session_dir)
    print(render(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
