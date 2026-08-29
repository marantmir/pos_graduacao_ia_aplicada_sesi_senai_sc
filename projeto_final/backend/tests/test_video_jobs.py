import time

from app.video_jobs import FINISHED_JOB_TTL_SECONDS, VideoJobRegistry


def test_finished_job_stays_available_within_ttl():
    registry = VideoJobRegistry()
    job = registry.create(max_frames=60)
    registry.complete(job.id, {"status": "processed"})

    fetched = registry.get(job.id)
    assert fetched is not None
    assert fetched.status == "done"
    assert fetched.result == {"status": "processed"}


def test_finished_job_is_purged_after_ttl():
    registry = VideoJobRegistry()
    job = registry.create(max_frames=60)
    registry.complete(job.id, {"status": "processed"})
    job.finished_at = time.monotonic() - (FINISHED_JOB_TTL_SECONDS + 1)

    registry.create(max_frames=60)

    assert registry.get(job.id) is None


def test_processing_job_is_never_purged():
    registry = VideoJobRegistry()
    job = registry.create(max_frames=60)
    job.updated_at = time.monotonic() - (FINISHED_JOB_TTL_SECONDS + 100)

    registry.create(max_frames=60)

    assert registry.get(job.id) is not None


def test_failed_job_records_error_and_finished_at():
    registry = VideoJobRegistry()
    job = registry.create(max_frames=60)
    registry.fail(job.id, "erro de teste")

    fetched = registry.get(job.id)
    assert fetched is not None
    assert fetched.status == "error"
    assert fetched.error == "erro de teste"
    assert fetched.finished_at is not None
