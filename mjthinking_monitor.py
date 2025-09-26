#!/usr/bin/env python3
"""Interactive monitor for MJThinking sessions.

Reads structured metadata emitted by `mjthinking.sh` (stored under
`runs/<session_id>/session.jsonl`) and renders a live progress view.

Usage examples:
    python3 mjthinking_monitor.py                   # show latest session snapshot
    python3 mjthinking_monitor.py --follow          # tail latest session live
    python3 mjthinking_monitor.py --session <id>    # inspect specific session
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

RUNS_DIR = Path(__file__).resolve().parent / "runs"


@dataclass
class RoundInfo:
    round_number: int
    chains: int
    majority_count: int
    majority_total: int
    majority_required: int
    majority_pass: bool
    referee_verdict: str
    referee_pass: bool
    numeric_verdict: str
    numeric_pass: bool
    elapsed_seconds: Optional[int]
    eta_seconds: Optional[int]
    timestamp: Optional[int]


@dataclass
class SessionState:
    session_id: Optional[str] = None
    question: Optional[str] = None
    chains: Optional[int] = None
    start_timestamp: Optional[int] = None
    rounds: Dict[int, RoundInfo] = field(default_factory=dict)
    completion_status: Optional[str] = None
    final_answer: Optional[str] = None
    final_referee: Optional[str] = None
    final_numeric: Optional[str] = None
    final_elapsed: Optional[int] = None
    completion_timestamp: Optional[int] = None

    def sorted_rounds(self) -> List[RoundInfo]:
        return [self.rounds[r] for r in sorted(self.rounds)]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor MJThinking session progress")
    parser.add_argument(
        "--session",
        help="Session ID or path to session directory. Defaults to the newest session in runs/",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Continuously stream updates (like tail -f)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds when --follow is used (default: 2.0)",
    )
    return parser.parse_args(argv)


def find_session_dir(session_arg: Optional[str]) -> Path:
    if session_arg:
        candidate = Path(session_arg)
        if candidate.is_dir():
            return candidate
        # try interpreting as session id under runs/
        candidate = RUNS_DIR / session_arg
        if candidate.is_dir():
            return candidate
        raise SystemExit(f"Session '{session_arg}' not found")

    if not RUNS_DIR.exists():
        raise SystemExit("runs/ directory does not exist yet. Launch a session first.")

    session_dirs = sorted(
        [p for p in RUNS_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not session_dirs:
        raise SystemExit("No session directories found under runs/. Start a session first.")
    return session_dirs[0]


def load_events(meta_path: Path, start_pos: int = 0):
    if not meta_path.exists():
        return [], start_pos
    with meta_path.open("r", encoding="utf-8") as fh:
        fh.seek(start_pos)
        lines = fh.readlines()
        new_pos = fh.tell()
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events, new_pos


def update_state(state: SessionState, events: List[dict]) -> None:
    for event in events:
        kind = event.get("event")
        if kind == "session_start":
            state.session_id = event.get("session_id")
            state.question = event.get("question")
            state.chains = event.get("chains")
            state.start_timestamp = event.get("timestamp")
        elif kind == "round_complete":
            round_num = int(event.get("round", -1))
            if round_num < 0:
                continue
            state.rounds[round_num] = RoundInfo(
                round_number=round_num,
                chains=int(event.get("chains", 0)),
                majority_count=int(event.get("majority_count", 0)),
                majority_total=int(event.get("majority_total", 0)),
                majority_required=int(event.get("majority_required", 0)),
                majority_pass=event.get("majority_pass", "NO") == "YES",
                referee_verdict=event.get("referee_verdict", "UNKNOWN"),
                referee_pass=event.get("referee_pass", "NO") == "YES",
                numeric_verdict=event.get("numeric_verdict", "UNKNOWN"),
                numeric_pass=event.get("numeric_pass", "NO") == "YES",
                elapsed_seconds=_safe_int(event.get("elapsed_seconds")),
                eta_seconds=_safe_int(event.get("eta_seconds")),
                timestamp=_safe_int(event.get("timestamp")),
            )
        elif kind == "session_complete":
            state.completion_status = event.get("status")
            state.final_answer = event.get("final_answer")
            state.final_referee = event.get("referee_verdict")
            state.final_numeric = event.get("numeric_verdict")
            state.final_elapsed = _safe_int(event.get("elapsed_seconds"))
            state.completion_timestamp = _safe_int(event.get("timestamp"))


def render(state: SessionState, session_dir: Path) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(" MJThinking Session Monitor")
    lines.append("=" * 72)
    lines.append(f"Session directory : {session_dir}")
    if state.session_id:
        lines.append(f"Session ID        : {state.session_id}")
    if state.question:
        lines.append(f"Question          : {state.question}")
    if state.chains is not None:
        lines.append(f"Initial chains    : {state.chains}")
    if state.start_timestamp:
        lines.append(f"Started at        : {format_ts(state.start_timestamp)}")

    lines.append("")
    rounds = state.sorted_rounds()
    if rounds:
        lines.append("Rounds:")
        lines.append("  #  Chains  Maj  (Needed)  Ref  Num  Elapsed   ETA")
        lines.append("  -- ------- ---- --------- ---- ---- -------- ------")
        for info in rounds:
            lines.append(
                f"  {info.round_number:>2} {info.chains:>7}"
                f" {info.majority_count:>4}/{info.majority_total:<4}"
                f" ({info.majority_required:>2})"
                f" {fmt_pass(info.majority_pass):>4}"
                f" {fmt_verdict(info.referee_verdict, info.referee_pass):>4}"
                f" {fmt_verdict(info.numeric_verdict, info.numeric_pass):>4}"
                f" {format_duration(info.elapsed_seconds):>8}"
                f" {format_duration(info.eta_seconds):>6}"
            )
    else:
        lines.append("No rounds recorded yet.")

    lines.append("")
    if state.completion_status:
        lines.append(f"Status            : {state.completion_status}")
        if state.final_elapsed is not None:
            lines.append(f"Total elapsed     : {format_duration(state.final_elapsed)}")
        if state.completion_timestamp:
            lines.append(f"Completed at      : {format_ts(state.completion_timestamp)}")
        if state.final_referee:
            lines.append(f"Final referee     : {state.final_referee}")
        if state.final_numeric:
            lines.append(f"Final numeric     : {state.final_numeric}")
        if state.final_answer:
            lines.append("")
            lines.append("Final Answer:")
            lines.extend(indent_lines(state.final_answer.strip()))
    else:
        lines.append("Status            : in_progress")

    lines.append("")
    lines.append("(Ctrl+C to exit)")
    return "\n".join(lines)


def indent_lines(text: str, indent: str = "    ") -> List[str]:
    return [indent + line for line in text.splitlines() if line.strip()]


def fmt_pass(value: bool) -> str:
    return "PASS" if value else "----"


def fmt_verdict(verdict: Optional[str], passed: bool) -> str:
    verdict = (verdict or "UNKNOWN").upper()
    if passed:
        return verdict[:4]
    if verdict == "PASS":
        return "----"
    return verdict[:4]


def format_duration(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "--"
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return "".join(parts)


def format_ts(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "--"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    session_dir = find_session_dir(args.session)
    meta_path = session_dir / "session.jsonl"
    if not meta_path.exists():
        print(f"No session.jsonl found in {session_dir}.", file=sys.stderr)
        return 1

    state = SessionState()
    position = 0

    def refresh():
        nonlocal position
        events, position = load_events(meta_path, position)
        if events:
            update_state(state, events)
        output = render(state, session_dir)
        sys.stdout.write("\033c")  # clear screen
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    try:
        refresh()
        if args.follow:
            while True:
                time.sleep(max(args.interval, 0.2))
                refresh()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
