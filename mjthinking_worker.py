#!/usr/bin/env python3
"""Queue worker for MJThinking sessions."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover (non-POSIX systems)
    fcntl = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
QUEUE_FILE = RUNS_DIR / "queue.jsonl"
LOG_DIR = RUNS_DIR / "queue_logs"
WORKER_ID = uuid.uuid4().hex[:8]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process MJThinking queue jobs")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one job and then exit",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds to sleep between queue polls when no work is available",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        help="Maximum number of jobs to process before exiting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the job that would be processed without launching mjthinking.sh",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose logging while running",
    )
    return parser.parse_args()


def log(msg: str, *, verbose: bool = True) -> None:
    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    if verbose:
        print(f"[{timestamp}] [worker:{WORKER_ID}] {msg}")
        sys.stdout.flush()


def ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def pop_job() -> dict | None:
    if not QUEUE_FILE.exists():
        return None
    if fcntl is None:
        raise SystemExit("fcntl is required on this platform to safely read the queue")

    with QUEUE_FILE.open("r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        lines = fh.readlines()
        fh.seek(0)
        fh.truncate()

        job_line: str | None = None
        remainder: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if job_line is None:
                job_line = line
            else:
                remainder.append(line)
        fh.writelines(remainder)
        fcntl.flock(fh, fcntl.LOCK_UN)

    if not job_line:
        return None

    try:
        job = json.loads(job_line)
    except json.JSONDecodeError as exc:
        log(f"Skipping invalid queue entry (JSON error: {exc})", verbose=True)
        return None

    if not isinstance(job, dict):
        log("Skipping invalid queue entry (expected JSON object)", verbose=True)
        return None

    job.setdefault("job_id", uuid.uuid4().hex)
    return job


def build_env(job: dict) -> dict[str, str]:
    env = os.environ.copy()
    style = job.get("style")
    if style:
        env["PROMPT_STYLE"] = str(style)
    mode = job.get("mode")
    if mode:
        env["MODE"] = str(mode)
    env_overrides = job.get("env") or {}
    if isinstance(env_overrides, dict):
        for key, value in env_overrides.items():
            if value is None:
                continue
            env[str(key)] = str(value)
    return env


def write_receipt(job: dict, **extra: object) -> Path:
    receipt_dir = LOG_DIR / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    payload = {"job": job, **extra}
    path = receipt_dir / f"{job['job_id']}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def process_job(job: dict, *, dry_run: bool, verbose: bool) -> int:
    prompt = job.get("prompt")
    if not prompt:
        log("Job missing 'prompt' field; skipping", verbose=verbose)
        return 0

    env = build_env(job)
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    job_id = job.get("job_id") or uuid.uuid4().hex
    log_path = LOG_DIR / f"{job_id}_{timestamp}.log"

    cmd = [str(BASE_DIR / "mjthinking.sh"), prompt]

    log(f"Processing job {job_id}: prompt length={len(prompt)}", verbose=verbose)
    if dry_run:
        log("Dry run enabled; skipping execution", verbose=verbose)
        write_receipt(job, status="dry_run", log=str(log_path))
        return 0

    log(f"Launching: {' '.join(cmd)}", verbose=verbose)
    with log_path.open("w", encoding="utf-8") as log_fh:
        log_fh.write(f"# MJThinking queue job\n# job_id={job_id}\n# timestamp={timestamp}\n\n")
        log_fh.flush()
        result = subprocess.run(
            cmd,
            env=env,
            cwd=str(BASE_DIR),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
    status = {
        "returncode": result.returncode,
        "log_file": str(log_path),
        "completed_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    write_receipt(job, status=status)

    if result.returncode == 0:
        log(f"Job {job_id} completed successfully", verbose=verbose)
    else:
        log(f"Job {job_id} failed with exit code {result.returncode}", verbose=verbose)
    return result.returncode


def main() -> int:
    args = parse_args()
    ensure_dirs()

    processed = 0
    while True:
        job = pop_job()
        if not job:
            if args.once or (args.max_jobs and processed >= args.max_jobs):
                break
            log("Queue empty", verbose=args.verbose)
            time.sleep(args.poll_interval)
            continue

        exit_code = process_job(job, dry_run=args.dry_run, verbose=args.verbose)
        processed += 1
        if exit_code != 0:
            log("Stopping due to job failure", verbose=True)
            return exit_code
        if args.once or (args.max_jobs and processed >= args.max_jobs):
            break

    log(f"Processed {processed} job(s)", verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
