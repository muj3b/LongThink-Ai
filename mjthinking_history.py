#!/usr/bin/env python3
"""Inspect historical MJThinking round durations."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import List

RUNS_DIR = Path(__file__).resolve().parent / "runs"
HISTORY_FILE = RUNS_DIR / "history_rounds.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show historical round duration statistics")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only consider the most recent N records",
    )
    return parser.parse_args()


def load_durations(limit: int | None) -> List[int]:
    if not HISTORY_FILE.exists():
        return []
    durations: List[int] = []
    with HISTORY_FILE.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "round_complete":
            continue
        duration = event.get("round_duration")
        if isinstance(duration, int) and duration > 0:
            durations.append(duration)
    return durations


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return "".join(parts)


def main() -> int:
    args = parse_args()
    durations = load_durations(args.limit)
    if not durations:
        print("No historical round data recorded yet.")
        return 0

    avg = statistics.mean(durations)
    med = statistics.median(durations)
    p90 = statistics.quantiles(durations, n=10)[8] if len(durations) >= 10 else max(durations)

    print("=== Historical Round Durations ===")
    print(f"Samples      : {len(durations)}")
    print(f"Average      : {format_duration(int(round(avg)))}")
    print(f"Median       : {format_duration(int(round(med)))}")
    print(f"90th percentile : {format_duration(int(round(p90)))}")
    if args.limit:
        print(f"(limited to last {args.limit} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
