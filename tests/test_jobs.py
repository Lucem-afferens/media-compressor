"""Tests for job progress / ETA."""

from __future__ import annotations

import time

from jobs import JobPhase, JobState


def test_snapshot_includes_eta_during_processing() -> None:
    job = JobState(id="t1", kind="video", phase=JobPhase.PROCESSING, percent=50.0)
    job.started_at = time.monotonic() - 10.0
    snap = job.snapshot()
    assert snap["eta_sec"] is not None
    assert snap["eta_sec"] > 0
    assert snap["done"] is False


def test_snapshot_no_eta_when_done() -> None:
    job = JobState(id="t2", kind="video", phase=JobPhase.DONE, percent=100.0)
    snap = job.snapshot()
    assert snap.get("eta_sec") is None
    assert snap["done"] is True
