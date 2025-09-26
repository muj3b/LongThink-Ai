#!/usr/bin/env python3
"""Enqueue prompts for MJThinking processing."""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
QUEUE_FILE = RUNS_DIR / "queue.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add a prompt to the MJThinking work queue")
    parser.add_argument("prompt", nargs="?", help="Prompt text to enqueue")
    parser.add_argument(
        "--file",
        help="Path to a text file containing the prompt (overrides positional prompt if both provided)",
    )
    parser.add_argument(
        "--style",
        help="Optional PROMPT_STYLE value to set when processing this job",
    )
    parser.add_argument(
        "--mode",
        help="Optional MODE environment override when processing the job",
    )
    parser.add_argument(
        "--metadata",
        help="Arbitrary JSON string to attach to the job metadata",
    )
    return parser.parse_args()


def load_prompt(args: argparse.Namespace) -> str:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise SystemExit(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    raise SystemExit("Provide a prompt via positional argument or --file")


def append_job(job: Dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with QUEUE_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(job, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    prompt = load_prompt(args)
    if not prompt:
        raise SystemExit("Prompt is empty")

    metadata: Dict[str, Any] = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON metadata: {exc}")

    job = {
        "job_id": uuid.uuid4().hex,
        "created_at": int(time.time()),
        "prompt": prompt,
        "style": args.style,
        "mode": args.mode,
        "metadata": metadata,
    }
    append_job(job)
    print(f"[queue] Enqueued job {job['job_id']}")
    print(f"[queue] Prompt: {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
