#!/usr/bin/env python3
"""Convenience CLI for controlling MJThinking sessions.

Writes control commands (`PAUSE`, `RESUME`, `STOP`) into the
`runs/<session_id>/control.ctl` file that `mjthinking.sh` polls.

Examples
--------
    python3 mjthinking_ctl.py pause
    python3 mjthinking_ctl.py resume --session mjthinking_20250925_210000_12345
    python3 mjthinking_ctl.py stop  # targets latest session by default
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

RUNS_DIR = Path(__file__).resolve().parent / "runs"
CONTROL_FILENAME = "control.ctl"


VALID_COMMANDS = {"pause": "PAUSE", "resume": "RESUME", "stop": "STOP", "abort": "ABORT"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send control commands to an MJThinking session")
    parser.add_argument("command", choices=VALID_COMMANDS.keys(), help="Command to send")
    parser.add_argument(
        "--session",
        help="Session ID or path. Defaults to the most recent session under runs/",
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

    session_dirs = sorted(
        [p for p in RUNS_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for directory in session_dirs:
        if (directory / CONTROL_FILENAME).exists():
            return directory
    raise SystemExit("No session with control file found. Start a session first.")


def write_command(session_dir: Path, command: str) -> None:
    control_path = session_dir / CONTROL_FILENAME
    control_path.write_text(f"{command}\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    session_dir = resolve_session_dir(args.session)
    control_command = VALID_COMMANDS[args.command]
    write_command(session_dir, control_command)
    print(f"[control] Wrote '{control_command}' to {session_dir / CONTROL_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
