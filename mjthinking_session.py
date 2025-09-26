#!/usr/bin/env python3
"""Session management utilities for the MJThinking pipeline.

This module offers both a programmatic API (via SessionManager) and a small
command-line interface for shell scripts to initialise sessions, append wave
metadata, store checkpoints, and finalise results.
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
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"


@dataclass
class RoundRecord:
    wave: int
    started_at: float
    duration: float
    majority_count: int
    total_chains: int
    referee: str
    numeric_check: str
    validators: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None
    leader: Optional[str] = None
    model: Optional[str] = None


class SessionManager:
    def __init__(self, session_id: str, create: bool = False) -> None:
        if not session_id:
            raise ValueError("session_id must be provided")
        self.session_id = session_id
        self.session_dir = RUNS_DIR / session_id
        self.manifest_path = self.session_dir / "manifest.json"
        self.state_path = self.session_dir / "state.json"
        self.rounds_dir = self.session_dir / "waves"
        self.outputs_dir = self.session_dir / "outputs"
        self.logs_dir = self.session_dir / "logs"
        if create:
            self._ensure_dirs()

    # ------------------------------------------------------------------ utils
    def _ensure_dirs(self) -> None:
        for folder in (self.session_dir, self.rounds_dir, self.outputs_dir, self.logs_dir):
            folder.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        raise FileNotFoundError(f"Manifest not initialised for session {self.session_id}")

    def _store_manifest(self, data: Dict[str, Any]) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(self.manifest_path)

    def get_manifest(self) -> Dict[str, Any]:
        return self._load_manifest()

    # ---------------------------------------------------------------- init
    def init_manifest(self, *, question: str, driver: str, params: Dict[str, Any]) -> None:
        self._ensure_dirs()
        now = time.time()
        manifest = {
            "session_id": self.session_id,
            "question": question,
            "driver": driver,
            "created_at": datetime.utcfromtimestamp(now).isoformat() + "Z",
            "started_at": now,
            "parameters": params,
            "rounds": [],
            "status": "running",
        }
        self._store_manifest(manifest)

    # ---------------------------------------------------------------- rounds
    def append_round(self, record: RoundRecord) -> None:
        manifest = self._load_manifest()
        manifest.setdefault("rounds", [])
        manifest["rounds"].append({
            "wave": record.wave,
            "started_at": record.started_at,
            "duration": record.duration,
            "majority_count": record.majority_count,
            "total_chains": record.total_chains,
            "referee": record.referee,
            "numeric_check": record.numeric_check,
            "validators": record.validators,
            "confidence": record.confidence,
            "leader": record.leader,
            "model": record.model,
        })
        self._store_manifest(manifest)

    # ---------------------------------------------------------------- state
    def save_state(self, state: Dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        tmp.replace(self.state_path)

    def load_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        raise FileNotFoundError("No checkpoint available for this session.")

    # --------------------------------------------------------------- finalize
    def finalize(
        self,
        *,
        final_answer: str,
        confidence: Optional[float],
        model: Optional[str],
        status: str,
    ) -> None:
        manifest = self._load_manifest()
        now = time.time()
        manifest.update(
            {
                "status": status,
                "final_answer": final_answer,
                "confidence": confidence,
                "model": model,
                "finished_at": now,
                "duration": now - manifest.get("started_at", now),
            }
        )
        self._store_manifest(manifest)
        self._emit_summary_files(manifest)

    def _emit_summary_files(self, manifest: Dict[str, Any]) -> None:
        summary_md = self.outputs_dir / "summary.md"
        result_json = self.outputs_dir / "result.json"
        # Markdown summary
        lines = [
            f"# MJThinking Session `{manifest['session_id']}`",
            "",
            f"**Question**: {manifest['question']}",
            f"**Driver**: {manifest.get('driver', 'unknown')}",
            f"**Status**: {manifest.get('status', 'unknown')}",
            f"**Duration**: {manifest.get('duration', 0):.1f} seconds",
            "",
            "## Final Answer",
            manifest.get("final_answer", "<no answer>") or "<no answer>",
            "",
            "## Waves",
        ]
        for round_info in manifest.get("rounds", []):
            lines.extend(
                [
                    f"- Wave {round_info['wave']}:",
                    f"  - Majority: {round_info['majority_count']}/{round_info['total_chains']}",
                    f"  - Confidence: {round_info.get('confidence')}",
                    f"  - Referee: {round_info.get('referee')}",
                    f"  - Numeric: {round_info.get('numeric_check')}",
                ]
            )
            if round_info.get("validators"):
                for validator in round_info["validators"]:
                    lines.append(
                        f"  - Validator `{validator['name']}`: {validator['status']} ({validator.get('detail','')})"
                    )
        summary_md.write_text("\n".join(lines))
        result_json.write_text(json.dumps(manifest, indent=2, sort_keys=True))


# ---------------------------------------------------------------- CLI helpers

def parse_key_value_pairs(pairs: List[str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        data[key] = value
    return data


def cmd_init(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session, create=True)
    params = parse_key_value_pairs(args.param or [])
    mgr.init_manifest(question=args.question, driver=args.driver, params=params)


def cmd_append_round(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session)
    record = RoundRecord(
        wave=args.wave,
        started_at=args.started_at,
        duration=args.duration,
        majority_count=args.majority,
        total_chains=args.total,
        referee=args.referee,
        numeric_check=args.numeric,
        validators=[json.loads(item) for item in args.validators or []],
        confidence=args.confidence,
        leader=args.leader,
        model=args.model,
    )
    mgr.append_round(record)


def cmd_checkpoint(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session)
    state = json.loads(Path(args.state).read_text()) if args.state else json.loads(args.json)
    mgr.save_state(state)


def cmd_finalize(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session)
    mgr.finalize(final_answer=args.answer, confidence=args.confidence, model=args.model, status=args.status)


def cmd_resume(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session)
    state = mgr.load_state()
    print(json.dumps(state, indent=2, sort_keys=True))


def cmd_show_manifest(args: argparse.Namespace) -> None:
    mgr = SessionManager(args.session)
    manifest = mgr.get_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MJThinking session utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialise a new session manifest")
    p_init.add_argument("--session", required=True)
    p_init.add_argument("--question", required=True)
    p_init.add_argument("--driver", required=True)
    p_init.add_argument("--param", action="append")
    p_init.set_defaults(func=cmd_init)

    p_append = sub.add_parser("append-round", help="Append a wave record to the manifest")
    p_append.add_argument("--session", required=True)
    p_append.add_argument("--wave", type=int, required=True)
    p_append.add_argument("--started-at", type=float, required=True)
    p_append.add_argument("--duration", type=float, required=True)
    p_append.add_argument("--majority", type=int, required=True)
    p_append.add_argument("--total", type=int, required=True)
    p_append.add_argument("--confidence", type=float)
    p_append.add_argument("--leader")
    p_append.add_argument("--model")
    p_append.add_argument("--referee", default="UNKNOWN")
    p_append.add_argument("--numeric", default="UNKNOWN")
    p_append.add_argument("--validators", action="append")
    p_append.set_defaults(func=cmd_append_round)

    p_checkpoint = sub.add_parser("checkpoint", help="Persist a checkpoint state JSON")
    p_checkpoint.add_argument("--session", required=True)
    group = p_checkpoint.add_mutually_exclusive_group(required=True)
    group.add_argument("--state", help="Path to JSON state file")
    group.add_argument("--json", help="Inline JSON string")
    p_checkpoint.set_defaults(func=cmd_checkpoint)

    p_finalize = sub.add_parser("finalize", help="Mark the session as completed")
    p_finalize.add_argument("--session", required=True)
    p_finalize.add_argument("--answer", required=True)
    p_finalize.add_argument("--confidence", type=float)
    p_finalize.add_argument("--model")
    p_finalize.add_argument("--status", default="completed")
    p_finalize.set_defaults(func=cmd_finalize)

    p_resume = sub.add_parser("resume", help="Emit the last checkpoint state as JSON")
    p_resume.add_argument("--session", required=True)
    p_resume.set_defaults(func=cmd_resume)

    p_manifest = sub.add_parser("show-manifest", help="Print the session manifest JSON")
    p_manifest.add_argument("--session", required=True)
    p_manifest.set_defaults(func=cmd_show_manifest)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
