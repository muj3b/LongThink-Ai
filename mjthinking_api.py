#!/usr/bin/env python3
"""FastAPI control plane for MJThinking."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
QUEUE_FILE = RUNS_DIR / "queue.jsonl"
LOG_DIR = RUNS_DIR / "queue_logs"
PROMPTS_DIR = BASE_DIR / "prompts"

app = FastAPI(title="MJThinking Control Plane", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_session_id() -> str:
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"mjthinking_{timestamp}_{suffix}"


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

    @property
    def summary_md(self) -> Path:
        return self.path / "summary.md"

    @property
    def summary_json(self) -> Path:
        return self.path / "summary.json"


class LaunchRequest(BaseModel):
    prompt: Optional[str]
    prompt_style: Optional[str] = None
    mode: Optional[str] = None
    env: Dict[str, str] | None = None
    queue_only: bool = False
    session_id: Optional[str] = None


class LaunchResponse(BaseModel):
    job_id: str
    queued: bool
    session_id: Optional[str] = None
    pid: Optional[int] = None


class QueueRequest(BaseModel):
    prompt: str
    prompt_style: Optional[str] = None
    mode: Optional[str] = None
    env: Dict[str, str] | None = None
    session_id: Optional[str] = None


class ResumeRequest(BaseModel):
    env: Dict[str, str] | None = None


class ControlRequest(BaseModel):
    command: str


class CleanupRequest(BaseModel):
    days: Optional[int] = None
    keep: Optional[int] = None
    sessions: List[str] | None = None
    dry_run: bool = False
    force: bool = False


class SessionSummary(BaseModel):
    session_id: str
    status: Optional[str]
    question: Optional[str]
    rounds: Optional[int]
    elapsed_seconds: Optional[int]


def enqueue_job(job: Dict[str, Any]) -> str:
    ensure_dirs()
    job = {k: v for k, v in job.items() if v is not None}
    job.setdefault("job_id", uuid.uuid4().hex)
    job.setdefault("enqueued_at", dt.datetime.utcnow().isoformat() + "Z")
    with QUEUE_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(job) + "\n")
    return job["job_id"]


def read_queue() -> List[Dict[str, Any]]:
    if not QUEUE_FILE.exists():
        return []
    jobs: List[Dict[str, Any]] = []
    with QUEUE_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                jobs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return jobs


def remove_queue_job(job_id: str) -> bool:
    if not QUEUE_FILE.exists():
        return False
    changed = False
    with QUEUE_FILE.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    with QUEUE_FILE.open("w", encoding="utf-8") as fh:
        for line in lines:
            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                fh.write(line)
                continue
            if job.get("job_id") == job_id:
                changed = True
                continue
            fh.write(line)
    return changed


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


def build_env(overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = os.environ.copy()
    if overrides:
        env.update({str(k): str(v) for k, v in overrides.items() if v is not None})
    return env


async def launch_process(command: List[str], env: Dict[str, str]) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(BASE_DIR),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    asyncio.create_task(process.wait())
    return process


def manifest_summary(manifest: Dict[str, Any]) -> SessionSummary:
    completion = manifest.get("completion", {})
    return SessionSummary(
        session_id=manifest.get("session_id", "unknown"),
        status=completion.get("status"),
        question=manifest.get("question"),
        rounds=completion.get("rounds"),
        elapsed_seconds=completion.get("elapsed_seconds"),
    )


def iter_sessions(limit: Optional[int] = None) -> Iterable[SessionSummary]:
    for idx, session in enumerate(find_sessions()):
        if limit is not None and idx >= limit:
            break
        try:
            manifest = read_manifest(session)
        except FileNotFoundError:
            continue
        summary = manifest_summary(manifest)
        if summary.session_id == "unknown":
            summary.session_id = session.session_id
        yield summary


@app.get("/sessions", response_model=List[SessionSummary])
def api_list_sessions(limit: int | None = None) -> List[SessionSummary]:
    summaries = list(iter_sessions(limit))
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
    payload["events"] = list_events(session, limit=400)
    if session.summary_md.exists():
        payload["summary_md"] = session.summary_md.read_text(encoding="utf-8")
    if session.summary_json.exists():
        try:
            payload["summary_json"] = json.loads(session.summary_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload["summary_json"] = None
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
        raise HTTPException(status_code=400, detail="prompt is required")

    if req.queue_only:
        job_id = enqueue_job(
            {
                "prompt": req.prompt,
                "style": req.prompt_style,
                "mode": req.mode,
                "env": req.env,
                "session_id": req.session_id,
            }
        )
        return LaunchResponse(job_id=job_id, queued=True, session_id=req.session_id)

    session_id = req.session_id or generate_session_id()
    env = build_env(req.env)
    env["SESSION_ID"] = session_id
    if req.prompt_style:
        env["PROMPT_STYLE"] = req.prompt_style
    if req.mode:
        env["MODE"] = req.mode

    cmd = [str(BASE_DIR / "mjthinking.sh"), req.prompt]
    process = await launch_process(cmd, env)
    return LaunchResponse(job_id=str(process.pid), queued=False, session_id=session_id, pid=process.pid)


@app.post("/sessions/{session_id}/resume", response_model=LaunchResponse)
async def api_resume_session(session_id: str, req: ResumeRequest | None = None) -> LaunchResponse:
    session_path = RUNS_DIR / session_id
    if not session_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    env = build_env((req.env if req else None))
    process = await launch_process([str(BASE_DIR / "mjthinking.sh"), "--resume", session_id], env)
    return LaunchResponse(job_id=str(process.pid), queued=False, session_id=session_id, pid=process.pid)


@app.post("/sessions/{session_id}/control")
def api_control_session(session_id: str, req: ControlRequest) -> Dict[str, str]:
    session = SessionInfo(session_id=session_id, path=RUNS_DIR / session_id)
    if not session.path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    ctl_path = session.path / "control.ctl"
    ctl_path.write_text(f"{req.command}\n", encoding="utf-8")
    return {"status": "ok", "command": req.command}


@app.get("/queue")
def api_queue_list() -> List[Dict[str, Any]]:
    return read_queue()


@app.post("/queue", response_model=LaunchResponse)
def api_queue_enqueue(req: QueueRequest) -> LaunchResponse:
    job_id = enqueue_job(req.dict())
    return LaunchResponse(job_id=job_id, queued=True, session_id=req.session_id)


@app.delete("/queue/{job_id}")
def api_queue_delete(job_id: str) -> Dict[str, Any]:
    removed = remove_queue_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "removed", "job_id": job_id}


@app.post("/cleanup")
def api_cleanup(req: CleanupRequest) -> Dict[str, Any]:
    ensure_dirs()
    cmd = [str(BASE_DIR / "mjthinking_gc.sh")]
    if req.days is not None:
        cmd.append(f"--days={req.days}")
    if req.keep is not None:
        cmd.append(f"--keep={req.keep}")
    for session_id in req.sessions or []:
        cmd.append(f"--session={session_id}")
    if req.dry_run:
        cmd.append("--dry-run")
    if req.force:
        cmd.append("--force")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "cleanup failed")
    return {"status": "ok", "output": result.stdout}


@app.get("/prompts")
def api_prompts() -> List[str]:
    ensure_dirs()
    styles = []
    for path in sorted(PROMPTS_DIR.glob("*.txt")):
        styles.append(path.stem)
    return styles


@app.get("/health")
def api_health() -> Dict[str, str]:
    return {"status": "ok"}



class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, session_id: str, message: Dict[str, Any]):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    try:
        session = SessionInfo(session_id=session_id, path=RUNS_DIR / session_id)
        # Send initial state
        if session.path.exists():
            events = list_events(session, limit=50)
            await websocket.send_json({"type": "init", "events": events})
        
        # Poll for new events (simple implementation for now)
        last_count = 0
        while True:
            if session.path.exists():
                current_events = list_events(session, limit=1000) # Read more to catch up
                if len(current_events) > last_count:
                    new_events = current_events[last_count:]
                    for event in new_events:
                        await websocket.send_json({"type": "event", "data": event})
                    last_count = len(current_events)
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(session_id, websocket)

if __name__ == "__main__":
    subprocess.run(["uvicorn", "mjthinking_api:app", "--reload", "--host", "0.0.0.0", "--port", "8000"], cwd=str(BASE_DIR))
