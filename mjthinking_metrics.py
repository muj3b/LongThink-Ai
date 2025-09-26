#!/usr/bin/env python3
"""Aggregate metrics across MJThinking sessions.

Reads the structured metadata emitted by `mjthinking.sh` (stored under
`runs/<session_id>/session.jsonl`) and reports aggregate/project-level
statistics. Useful for tracking success rates, average runtimes, and
confidence trends across multiple long-thinking sessions.

Examples
--------
    python3 mjthinking_metrics.py
    python3 mjthinking_metrics.py --limit 10
    python3 mjthinking_metrics.py --json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

RUNS_DIR = Path(__file__).resolve().parent / "runs"


@dataclass
class SessionSummary:
    session_id: str
    status: str
    question: Optional[str]
    rounds: Optional[int]
    elapsed_seconds: Optional[int]
    referee: Optional[str]
    numeric: Optional[str]
    start_ts: Optional[int]
    end_ts: Optional[int]

    @property
    def ok(self) -> bool:
        return self.status == "success"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate MJThinking session metrics")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only analyze the N most recent sessions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit metrics in JSON instead of human-readable text",
    )
    return parser.parse_args()


def discover_sessions(limit: Optional[int]) -> List[Path]:
    if not RUNS_DIR.exists():
        return []
    sessions = [p for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "session.jsonl").exists()]
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if limit:
        sessions = sessions[: max(limit, 0)]
    return sessions


def load_session(session_dir: Path) -> Optional[SessionSummary]:
    meta_path = session_dir / "session.jsonl"
    if not meta_path.exists():
        return None

    question = None
    rounds = None
    elapsed = None
    status = None
    referee = None
    numeric = None
    start_ts = None
    end_ts = None

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
                question = event.get("question")
                start_ts = event.get("timestamp")
            elif kind == "round_complete":
                rounds = event.get("round") or rounds
            elif kind == "session_complete":
                status = event.get("status")
                elapsed = event.get("elapsed_seconds")
                referee = event.get("referee_verdict")
                numeric = event.get("numeric_verdict")
                rounds = event.get("rounds", rounds)
                end_ts = event.get("timestamp")

    if status is None:
        status = "unknown"

    return SessionSummary(
        session_id=session_dir.name,
        status=status,
        question=question,
        rounds=int(rounds) if rounds is not None else None,
        elapsed_seconds=int(elapsed) if elapsed is not None else None,
        referee=referee,
        numeric=numeric,
        start_ts=int(start_ts) if start_ts is not None else None,
        end_ts=int(end_ts) if end_ts is not None else None,
    )


def aggregate(summaries: Iterable[SessionSummary]) -> Dict[str, object]:
    summaries = list(summaries)
    total = len(summaries)
    successes = sum(1 for s in summaries if s.ok)
    best_effort = sum(1 for s in summaries if s.status == "best_effort")
    stopped = sum(1 for s in summaries if s.status == "stopped")

    elapsed_values = [s.elapsed_seconds for s in summaries if s.elapsed_seconds is not None]
    round_values = [s.rounds for s in summaries if s.rounds is not None]

    def safe_mean(values: List[int]) -> Optional[float]:
        return statistics.mean(values) if values else None

    def safe_median(values: List[int]) -> Optional[float]:
        return statistics.median(values) if values else None

    result = {
        "sessions": total,
        "successes": successes,
        "best_effort": best_effort,
        "stopped": stopped,
        "success_rate": (successes / total) if total else None,
        "average_elapsed": safe_mean(elapsed_values),
        "median_elapsed": safe_median(elapsed_values),
        "average_rounds": safe_mean(round_values),
        "median_rounds": safe_median(round_values),
        "by_status": {},
        "recent": summaries,
    }

    status_counts: Dict[str, int] = {}
    for s in summaries:
        status_counts[s.status] = status_counts.get(s.status, 0) + 1
    result["by_status"] = status_counts

    return result


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--"
    seconds = int(round(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return "".join(parts)


def render_text(metrics: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("=== MJThinking Session Metrics ===")
    lines.append(f"Total sessions : {metrics['sessions']}")
    lines.append(f"Successes      : {metrics['successes']}")
    lines.append(f"Best-effort    : {metrics['best_effort']}")
    lines.append(f"Stopped        : {metrics['stopped']}")

    success_rate = metrics.get("success_rate")
    if success_rate is not None:
        lines.append(f"Success rate   : {success_rate:.1%}")
    else:
        lines.append("Success rate   : --")

    lines.append(f"Avg elapsed    : {format_duration(metrics.get('average_elapsed'))}")
    lines.append(f"Median elapsed : {format_duration(metrics.get('median_elapsed'))}")

    avg_rounds = metrics.get("average_rounds")
    med_rounds = metrics.get("median_rounds")
    lines.append(f"Avg rounds     : {avg_rounds:.2f}" if avg_rounds is not None else "Avg rounds     : --")
    lines.append(f"Median rounds  : {med_rounds}" if med_rounds is not None else "Median rounds  : --")

    lines.append("")
    lines.append("By status:")
    for status, count in sorted(metrics.get("by_status", {}).items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {status:<12} {count}")

    recent: List[SessionSummary] = metrics.get("recent", [])  # type: ignore[assignment]
    if recent:
        lines.append("")
        lines.append("Recent sessions:")
        lines.append("  ID                           Status       Rounds  Elapsed")
        lines.append("  --------------------------- ----------- ------- --------")
        for s in recent:
            lines.append(
                f"  {s.session_id:<27} {s.status:<11}"
                f" {s.rounds if s.rounds is not None else '--':>7}"
                f" {format_duration(s.elapsed_seconds):>8}"
            )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    session_dirs = discover_sessions(args.limit)
    summaries = [s for sd in session_dirs if (s := load_session(sd)) is not None]

    metrics = aggregate(summaries)

    if args.json:
        output = {
            **{k: v for k, v in metrics.items() if k != "recent"},
            "recent": [
                {
                    "session_id": s.session_id,
                    "status": s.status,
                    "rounds": s.rounds,
                    "elapsed_seconds": s.elapsed_seconds,
                    "question": s.question,
                }
                for s in summaries
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(render_text(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
