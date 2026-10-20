"""Background report jobs with real, measured progress.

A full research report can take seconds to minutes: it runs dozens of analysis
components per symbol, builds charts, and writes XLSX/PDF/ZIP files. Doing that
inside the HTTP request would time out and give the browser no feedback.

This module is a small, process-local job runner:

* each job has a UUID, a kind, params, status, stage and a 0-100 progress value;
* progress is ``completed_steps / total_steps`` where a step is a unit of work
  that actually finished (one symbol, one export) — never a timer;
* metadata is persisted as JSON under ``data/jobs`` so a page refresh can list
  and re-open a job;
* artifacts are written to ``data/exports/<job>/`` and served by job id only;
* a job that was RUNNING when the process died is marked INTERRUPTED on the next
  start instead of pretending it is still going.

The runner is deliberately in-process. The API is a single FastAPI process and
DuckDB allows only one writer per file, so a separate worker process would add
complexity without adding throughput. Jobs are bounded and cleaned up.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from megatool.config import PATHS

__all__ = [
    "Job",
    "JobError",
    "create_job",
    "get_job",
    "list_jobs",
    "update_job",
    "complete_job",
    "fail_job",
    "start_job",
    "artifact_path",
    "jobs_dir",
    "exports_dir",
    "sweep_jobs",
    "MAX_JOBS",
    "JOB_TTL_HOURS",
]

MAX_JOBS = 40
JOB_TTL_HOURS = 48
_LOCK = threading.RLock()
_ACTIVE: dict[str, threading.Thread] = {}


class JobError(ValueError):
    """Unknown job, unknown artifact, or an invalid state transition."""


def jobs_dir() -> Path:
    root = Path(os.getenv("MEGATOOL_JOBS_DIR", "")) if os.getenv("MEGATOOL_JOBS_DIR") else None
    path = root or (Path(PATHS.data) / "jobs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir(job_id: str | None = None) -> Path:
    root = Path(os.getenv("MEGATOOL_JOB_EXPORTS_DIR", "")) if os.getenv("MEGATOOL_JOB_EXPORTS_DIR") else None
    base = root or (Path(PATHS.exports) / "research")
    path = base / job_id if job_id else base
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "INTERRUPTED", "CANCELLED")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "QUEUED"
    progress: float = 0.0
    stage: str = "queued"
    message: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    finished_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    steps_total: int = 0
    steps_done: int = 0
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(job_id: str) -> Path:
    if not job_id or not all(c in "0123456789abcdef" for c in job_id.lower()) or len(job_id) != 32:
        raise JobError("invalid job id")
    return jobs_dir() / f"{job_id}.json"


def _write(job: Job) -> None:
    job.updated_at = _now()
    path = _path(job.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job.to_dict(), indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read(job_id: str) -> Job:
    path = _path(job_id)
    if not path.is_file():
        raise JobError("job not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"job record is unreadable: {exc}") from exc
    known = {f for f in Job.__dataclass_fields__}  # type: ignore[attr-defined]
    return Job(**{k: v for k, v in data.items() if k in known})


def _recover_interrupted() -> None:
    """Mark jobs that were running when the previous process stopped."""
    for path in jobs_dir().glob("*.json"):
        try:
            job = _read(path.stem)
        except JobError:
            continue
        if job.status in ("QUEUED", "RUNNING"):
            job.status = "INTERRUPTED"
            job.stage = "interrupted"
            job.message = (
                "The server restarted while this job was running. Its partial "
                "output was discarded; start the report again."
            )
            job.finished_at = _now()
            _write(job)


_RECOVERED = False


def _ensure_recovered() -> None:
    global _RECOVERED
    if _RECOVERED:
        return
    with _LOCK:
        if not _RECOVERED:
            _recover_interrupted()
            _RECOVERED = True


def create_job(kind: str, params: dict[str, Any] | None = None, *,
               steps_total: int = 0, stage: str = "queued") -> Job:
    """Create and persist a QUEUED job. The caller starts it with ``start_job``."""
    _ensure_recovered()
    with _LOCK:
        sweep_jobs()
        job = Job(id=uuid.uuid4().hex, kind=str(kind), params=dict(params or {}),
                  steps_total=max(0, int(steps_total)), stage=stage)
        _write(job)
        return job


def get_job(job_id: str) -> Job:
    _ensure_recovered()
    return _read(job_id)


def list_jobs(kind: str | None = None, limit: int = 20) -> list[Job]:
    _ensure_recovered()
    jobs: list[Job] = []
    for path in jobs_dir().glob("*.json"):
        try:
            job = _read(path.stem)
        except JobError:
            continue
        if kind and job.kind != kind:
            continue
        jobs.append(job)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[: max(1, min(int(limit), 100))]


def update_job(job_id: str, *, steps_done: int | None = None, stage: str | None = None,
               message: str | None = None, status: str | None = None) -> Job:
    """Record completed work. ``progress`` is derived, never supplied directly."""
    with _LOCK:
        job = _read(job_id)
        if job.status in ("SUCCEEDED", "FAILED", "INTERRUPTED", "CANCELLED"):
            return job
        if steps_done is not None:
            job.steps_done = max(job.steps_done, min(int(steps_done), job.steps_total or int(steps_done)))
        if job.steps_total > 0:
            job.progress = round(min(100.0, job.steps_done / job.steps_total * 100.0), 1)
        if stage:
            job.stage = str(stage)
        if message is not None:
            job.message = str(message)
        if status:
            if status not in STATUSES:
                raise JobError(f"invalid status {status!r}")
            job.status = status
        _write(job)
        return job


def complete_job(job_id: str, artifacts: dict[str, Path],
                 message: str = "Report ready") -> Job:
    """Finish a job, recording only artifact paths that actually exist."""
    with _LOCK:
        job = _read(job_id)
        base = exports_dir(job_id).resolve()
        recorded: dict[str, dict[str, Any]] = {}
        for fmt, path in artifacts.items():
            p = Path(path).resolve()
            if not p.is_file():
                raise JobError(f"artifact {fmt} was not written: {p}")
            if base not in p.parents:
                raise JobError("artifact escaped the job export directory")
            recorded[str(fmt)] = {
                "filename": p.name,
                "bytes": p.stat().st_size,
                "url": f"/api/baba/research/jobs/{job_id}/download/{fmt}",
            }
        job.artifacts = recorded
        job.status = "SUCCEEDED"
        job.stage = "done"
        job.progress = 100.0
        job.steps_done = job.steps_total or job.steps_done
        job.message = message
        job.finished_at = _now()
        _write(job)
        return job


def fail_job(job_id: str, error: str) -> Job:
    with _LOCK:
        job = _read(job_id)
        job.status = "FAILED"
        job.stage = "failed"
        job.error = str(error)[:2000]
        job.message = "The report could not be built. The reason is shown below."
        job.finished_at = _now()
        _write(job)
        return job


def start_job(job_id: str, work: Callable[[str], dict[str, Path]]) -> None:
    """Run ``work(job_id)`` in a daemon thread.

    ``work`` must call :func:`update_job` after each completed unit and return
    the artifact map. Any exception fails the job with its real message.
    """
    job = get_job(job_id)
    if job.status != "QUEUED":
        raise JobError(f"job is {job.status}, not QUEUED")

    def _runner() -> None:
        try:
            update_job(job_id, status="RUNNING", stage="starting",
                       message="Starting the report build")
            artifacts = work(job_id)
            complete_job(job_id, artifacts)
        except Exception as exc:  # noqa: BLE001 - recorded for the client
            fail_job(job_id, f"{type(exc).__name__}: {exc}")
        finally:
            with _LOCK:
                _ACTIVE.pop(job_id, None)

    thread = threading.Thread(target=_runner, name=f"report-{job_id[:8]}", daemon=True)
    with _LOCK:
        _ACTIVE[job_id] = thread
    thread.start()


def artifact_path(job_id: str, fmt: str) -> Path:
    """Resolve a recorded artifact. Refuses anything not written by this job."""
    job = get_job(job_id)
    fmt = str(fmt).lower()
    meta = job.artifacts.get(fmt)
    if not meta:
        raise JobError(f"no {fmt} artifact for this job")
    p = (exports_dir(job_id) / str(meta["filename"])).resolve()
    base = exports_dir(job_id).resolve()
    if base not in p.parents or not p.is_file():
        raise JobError("artifact is missing")
    return p


def sweep_jobs(max_age_hours: float = JOB_TTL_HOURS, keep: int = MAX_JOBS) -> int:
    """Delete expired job records and their exports. Returns the count removed."""
    cutoff = datetime.now(UTC) - timedelta(hours=max(1.0, float(max_age_hours)))
    removed = 0
    records: list[tuple[Path, Job]] = []
    for path in jobs_dir().glob("*.json"):
        try:
            records.append((path, _read(path.stem)))
        except JobError:
            continue
    records.sort(key=lambda p: p[1].created_at, reverse=True)
    for idx, (path, job) in enumerate(records):
        try:
            created = datetime.fromisoformat(job.created_at)
        except ValueError:
            created = cutoff - timedelta(seconds=1)
        expired = created < cutoff
        excess = idx >= keep
        if not (expired or excess):
            continue
        try:
            path.unlink(missing_ok=True)
            shutil.rmtree(exports_dir(job.id), ignore_errors=True)
            removed += 1
        except OSError:
            continue
    return removed
