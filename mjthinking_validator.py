#!/usr/bin/env python3
"""Validator runner for MJThinking.

This tool executes a suite of built-in validators and optional shell commands to
produce PASS/FAIL assessments on intermediate or final answers.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ValidatorResult:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def length_validator(question: str, answer: str, minimum: int) -> ValidatorResult:
    stripped = answer.strip()
    if len(stripped) >= minimum:
        return ValidatorResult("length", "PASS", f"len={len(stripped)} >= {minimum}")
    return ValidatorResult("length", "FAIL", f"len={len(stripped)} < {minimum}")


def keyword_validator(question: str, answer: str, keywords: List[str]) -> ValidatorResult:
    missing = [kw for kw in keywords if kw.lower() not in answer.lower()]
    if missing:
        return ValidatorResult(
            "keywords",
            "WARN",
            f"missing keywords: {', '.join(missing)}",
        )
    return ValidatorResult("keywords", "PASS", "all required keywords present")


def run_shell_validator(command: str, question: str, answer: str, timeout: int) -> ValidatorResult:
    env = os.environ.copy()
    env["MJTHINKING_QUESTION"] = question
    env["MJTHINKING_ANSWER"] = answer
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ValidatorResult(command, "WARN", "validator timed out")
    status = "PASS" if completed.returncode == 0 else "FAIL"
    detail = completed.stdout.strip() or completed.stderr.strip()
    return ValidatorResult(command, status, detail)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MJThinking validator runner")
    parser.add_argument("--question", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument(
        "--min-length",
        type=int,
        default=int(os.environ.get("MJTHINKING_VALIDATOR_MIN_LEN", "1")),
        help="Minimum length for the built-in length validator",
    )
    parser.add_argument(
        "--keywords",
        action="append",
        default=[],
        help="Ensure each keyword appears in the answer (case-insensitive)",
    )
    parser.add_argument(
        "--shell",
        action="append",
        default=os.environ.get("MJTHINKING_EXTRA_VALIDATORS", "").split(";;")
        if os.environ.get("MJTHINKING_EXTRA_VALIDATORS")
        else [],
        help="Shell validator command(s). Separated by ';;' when using env var.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("MJTHINKING_VALIDATOR_TIMEOUT", "30")),
        help="Per-shell-validator timeout in seconds",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON array of results")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    results: List[ValidatorResult] = []

    if args.min_length > 0:
        results.append(length_validator(args.question, args.answer, args.min_length))

    if args.keywords:
        results.append(keyword_validator(args.question, args.answer, args.keywords))

    for cmd in filter(None, args.shell):
        results.append(run_shell_validator(cmd, args.question, args.answer, args.timeout))

    if args.json or True:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        for res in results:
            print(f"[{res.status}] {res.name}: {res.detail}")


if __name__ == "__main__":
    main()
