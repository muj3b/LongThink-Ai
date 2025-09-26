#!/usr/bin/env python3
"""Example plugin that logs basic round data."""
import json
import os
import sys
from pathlib import Path

HOOK = os.environ.get("HOOK", "")
DEFAULT_SESSION_DIR = Path(os.environ.get("MJTHINKING_SESSION_DIR", ""))


def append(session_dir: Path, payload: dict) -> None:
    if not session_dir:
        return
    log_path = session_dir / "plugin_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def main(argv: list[str]) -> None:
    if not argv:
        return

    session_dir = Path(argv[0]) if argv[0] else DEFAULT_SESSION_DIR

    if HOOK == "post_round" and len(argv) >= 5:
        round_no, final_answer, conf_ratio, validators_pass = argv[1:5]
        append(
            session_dir,
            {
                "hook": HOOK,
                "round": int(round_no),
                "final_answer": final_answer,
                "confidence": float(conf_ratio),
                "validators_pass": validators_pass,
            },
        )
    elif HOOK == "session_complete" and len(argv) >= 3:
        status, reason = argv[1:3]
        append(
            session_dir,
            {
                "hook": HOOK,
                "status": status,
                "reason": reason,
            },
        )
    else:
        append(
            session_dir,
            {
                "hook": HOOK,
                "message": "No action for hook or insufficient args",
            },
        )


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as exc:  # noqa: BLE001
        fallback_dir = DEFAULT_SESSION_DIR or Path.cwd()
        append(fallback_dir, {"hook": HOOK, "error": str(exc)})
