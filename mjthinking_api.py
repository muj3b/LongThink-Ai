#!/usr/bin/env python3
"""FastAPI control plane for MJThinking."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
QUEUE_FILE = RUNS_DIR / "queue.jsonl"
LOG_DIR = RUNS_DIR / "queue_logs"

app = FastAPI(title="MJThinking Control Plane", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"],
)


@dataclass
class SessionInfo:
    session_id: str
    path: Path

    @property
    def manifest_path(self) -> Path:
        return self.path / "manifest.json"

    @property
    def state_path(self) -> Path:
        return self.path / "state.json"

    @property
    def events_path(self) -> Path:
        return self.path / "session.jsonl"


class LaunchRequest(BaseModel):
    prompt: str
    prompt_style: Optional[str] = None
    mode: Optional[str] = None
    env: Dict[str, str] | None = None
    queue_only: bool = True


class LaunchResponse(BaseModel):
    job_id: str
    queued: bool


class SessionSummary(BaseModel):
    session_id: str
    status: Optional[str]
    question: Optional[str]
    rounds: Optional[int]
    elapsed_seconds: Optional[int]


def ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def enqueue_job(job: Dict[str, Any]) -> str:
    ensure_dirs()
    job_id = job.get("job_id")
    if not job_id:
        import uuid

        job_id = uuid.uuid4().hex
        job["job_id"] = job_id
    with QUEUE_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(job) + "\n")
    return job_id


def find_sessions() -> List[SessionInfo]:
    ensure_dirs()
    sessions: List[SessionInfo] = []
    for path in RUNS_DIR.glob("mjthinking_*/"):
        sessions.append(SessionInfo(session_id=path.name.rstrip("/"), path=path))
    return sorted(sessions, key=lambda s: s.path.stat().st_mtime, reverse=True)


def read_manifest(session: SessionInfo) -> Dict[str, Any]:
    if not session.manifest_path.exists():
        raise FileNotFoundError("manifest not found")
    with session.manifest_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def read_state(session: SessionInfo) -> Dict[str, Any] | None:
    if not session.state_path.exists():
        return None
    with session.state_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def list_events(session: SessionInfo, limit: int = 200) -> List[Dict[str, Any]]:
    if not session.events_path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with session.events_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events[-limit:]


@app.get("/sessions", response_model=List[SessionSummary])
def api_list_sessions() -> List[SessionSummary]:
    summaries: List[SessionSummary] = []
    for session in find_sessions():
        try:
            manifest = read_manifest(session)
        except FileNotFoundError:
            continue
        completion = manifest.get("completion", {})
        summaries.append(
            SessionSummary(
                session_id=session.session_id,
                status=completion.get("status"),
                question=manifest.get("question"),
                rounds=completion.get("rounds"),
                elapsed_seconds=completion.get("elapsed_seconds"),
            )
        )
    return summaries


@app.get("/sessions/{session_id}")
def api_get_session(session_id: str) -> Dict[str, Any]:
    session = SessionInfo(session_id=session_id, path=RUNS_DIR / session_id)
    if not session.path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    payload: Dict[str, Any] = {"session_id": session_id}
    try:
        payload["manifest"] = read_manifest(session)
    except FileNotFoundError:
        payload["manifest"] = None
    payload["state"] = read_state(session)
    payload["events"] = list_events(session)
    return payload


@app.get("/sessions/{session_id}/events")
def api_session_events(session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    session = SessionInfo(session_id=session_id, path=RUNS_DIR / session_id)
    if not session.path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    return list_events(session, limit=limit)


@app.post("/sessions", response_model=LaunchResponse)
async def api_launch_session(req: LaunchRequest) -> LaunchResponse:
    if not req.prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    job: Dict[str, Any] = {"prompt": req.prompt, "style": req.prompt_style, "mode": req.mode, "env": req.env or {}}
    if req.queue_only:
        job_id = enqueue_job(job)
        return LaunchResponse(job_id=job_id, queued=True)

    cmd = [str(BASE_DIR / "mjthinking.sh"), req.prompt]
    env = os.environ.copy()
    if req.prompt_style:
        env["PROMPT_STYLE"] = req.prompt_style
    if req.mode:
        env["MODE"] = req.mode
    if req.env:
        env.update({str(k): str(v) for k, v in req.env.items()})

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(BASE_DIR),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    asyncio.create_task(process.wait())
    return LaunchResponse(job_id=str(process.pid), queued=False)


@app.post("/sessions/{session_id}/control")
def api_control_session(session_id: str, command: str) -> Dict[str, str]:
    session = SessionInfo(session_id=session_id, path=RUNS_DIR / session_id)
    if not session.path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    ctl_path = session.path / "control.ctl"
    ctl_path.write_text(f"{command}\n", encoding="utf-8")
    return {"status": "ok", "command": command}


@app.get("/health")
def api_health() -> Dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    subprocess.run(["uvicorn", "mjthinking_api:app", "--reload"], cwd=str(BASE_DIR))
