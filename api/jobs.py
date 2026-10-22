"""In-memory tracking of ingest jobs. Lost on restart, which is fine for a local tool."""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from jarvis_memory.service import MemoryService


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    indexed = "indexed"
    duplicate = "duplicate"
    failed = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class IngestJob:
    id: str
    filename: str
    stored_path: Path
    document_id: str
    status: JobStatus = JobStatus.queued
    error: str | None = None
    duplicate_of: str | None = None
    chunk_count: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


class JobStore:
    def __init__(self, max_jobs: int) -> None:
        self._jobs: OrderedDict[str, IngestJob] = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def create(self, filename: str, stored_path: Path, document_id: str) -> IngestJob:
        job = IngestJob(id=uuid.uuid4().hex, filename=filename, stored_path=stored_path, document_id=document_id)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self._max_jobs:
                self._jobs.popitem(last=False)
        return replace(job)

    def get(self, job_id: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return replace(job) if job else None

    def list(self) -> list[IngestJob]:
        with self._lock:
            return [replace(j) for j in reversed(self._jobs.values())]

    def update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = _now()


def process_jobs(service: MemoryService, jobs: JobStore, job_ids: list[str]) -> None:
    """Background task: ingest queued uploads one after another."""
    for job_id in job_ids:
        job = jobs.get(job_id)
        if job is None:
            continue
        jobs.update(job_id, status=JobStatus.processing)
        try:
            result = service.ingest_upload(job.stored_path, document_id=job.document_id)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via job status
            jobs.update(job_id, status=JobStatus.failed, error=f"{type(exc).__name__}: {exc}")
            continue
        if result.action == "duplicate":
            jobs.update(job_id, status=JobStatus.duplicate, duplicate_of=result.duplicate_of)
        else:
            jobs.update(job_id, status=JobStatus.indexed, chunk_count=result.chunk_count)
