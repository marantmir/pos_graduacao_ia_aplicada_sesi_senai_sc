"""In-memory job registry for video-vision processing.

OpenCV processing is CPU-bound and synchronous, so a job runs on a plain
background thread (no Celery/Redis needed for a single-process deployment)
while the request that started it gets a job id back immediately. Progress
is polled by an SSE endpoint so the frontend can show a live progress bar
instead of blocking on the full result.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field


# Finished jobs stay available for this long so a client whose SSE connection
# dropped right before the final event can reconnect and still get the result.
FINISHED_JOB_TTL_SECONDS = 180.0


@dataclass
class VideoJob:
    id: str
    max_frames: int
    status: str = "processing"  # processing | done | error
    processed: int = 0
    message: str = ""
    result: dict | None = None
    error: str | None = None
    updated_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None


class VideoJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._lock = threading.Lock()

    def create(self, max_frames: int) -> VideoJob:
        job = VideoJob(id=uuid.uuid4().hex, max_frames=max_frames)
        with self._lock:
            self._purge_finished_locked()
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> VideoJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_progress(self, job_id: str, processed: int, message: str = "") -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.processed = processed
                job.message = message
                job.updated_at = time.monotonic()

    def complete(self, job_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "done"
                job.result = result
                job.updated_at = time.monotonic()
                job.finished_at = job.updated_at

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "error"
                job.error = error
                job.updated_at = time.monotonic()
                job.finished_at = job.updated_at

    def discard(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def _purge_finished_locked(self, ttl: float = FINISHED_JOB_TTL_SECONDS) -> None:
        now = time.monotonic()
        stale = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and now - job.finished_at > ttl
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)


video_jobs = VideoJobRegistry()
