from datetime import datetime, timedelta, timezone

import pytest

from analytics.pipeline_status.gitlab_queries import (
    FailedJob,
    Pipeline,
    PullRequestPipeline,
    gitlab_ref_path_pattern,
    gitlab_ref_pattern,
)


@pytest.mark.parametrize(
    ("pr_number", "expected"),
    [
        (1, r"pr1\_%"),
        (12, r"pr12\_%"),
        (12345, r"pr12345\_%"),
    ],
)
def test_gitlab_ref_pattern_escapes_the_underscore(pr_number, expected):
    # An unescaped underscore is a single-character wildcard in LIKE, which would make
    # the pattern for PR 12 also match PR 123's ref.
    assert gitlab_ref_pattern(pr_number) == expected


def test_gitlab_ref_path_pattern_is_fully_qualified():
    # ci_refs stores "refs/heads/<branch>", not the bare branch name.
    assert gitlab_ref_path_pattern(12345) == r"refs/heads/pr12345\_%"


def _pipeline(**overrides) -> Pipeline:
    defaults = {
        "id": 1000,
        "status": "failed",
        "created_at": datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        "started_at": datetime(2026, 9, 25, 10, 1, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 9, 25, 11, 1, tzinfo=timezone.utc),
        "duration": 3600,
    }
    return Pipeline(**(defaults | overrides))


def test_elapsed_seconds_prefers_gitlabs_own_duration():
    assert _pipeline(duration=42).elapsed_seconds == 42


def test_elapsed_seconds_falls_back_to_time_so_far_while_running():
    # GitLab only writes `duration` once a pipeline finishes.
    started = datetime.now(timezone.utc) - timedelta(seconds=90)
    elapsed = _pipeline(duration=None, started_at=started, finished_at=None).elapsed_seconds

    assert elapsed == pytest.approx(90, abs=5)


def test_elapsed_seconds_is_unknown_before_a_pipeline_starts():
    assert _pipeline(duration=None, started_at=None, finished_at=None).elapsed_seconds is None


def _failed_job(**overrides) -> FailedJob:
    defaults = {
        "id": 1,
        "name": "build-pkg",
        "stage": "build",
        "failure_reason": "script_failure",
        "allow_failure": False,
        "pipeline_id": 1001,
        "is_trigger_job": False,
        "started_at": datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 9, 25, 10, 5, tzinfo=timezone.utc),
    }
    return FailedJob(**(defaults | overrides))


def test_failed_job_elapsed_seconds():
    assert _failed_job().elapsed_seconds == 300


def test_failed_job_elapsed_seconds_is_unknown_while_unfinished():
    assert _failed_job(finished_at=None).elapsed_seconds is None


def _pull_request_pipeline(**overrides) -> PullRequestPipeline:
    defaults = {
        "project_path": "spack/spack-packages",
        "pr_number": 12345,
        "ref": "pr12345_fix/foo",
        "sha": "abc123de" * 5,
        "root": _pipeline(),
        "child_pipelines": [],
        "job_status_counts": {"success": 3, "failed": 2, "running": 1, "skipped": 4},
        "failed_jobs": [
            _failed_job(id=1, name="blocking-one"),
            _failed_job(id=2, name="allowed-one", allow_failure=True),
        ],
        "failed_jobs_truncated": False,
    }
    return PullRequestPipeline(**(defaults | overrides))


def test_total_jobs_sums_every_state():
    assert _pull_request_pipeline().total_jobs == 10


def test_failed_and_in_progress_counts():
    pipeline = _pull_request_pipeline()

    assert pipeline.failed_job_count == 2
    # `skipped` is finished, not in progress; `running` is.
    assert pipeline.in_progress_job_count == 1


def test_in_progress_count_includes_every_unfinished_state():
    pipeline = _pull_request_pipeline(
        job_status_counts={
            "created": 1,
            "waiting_for_resource": 1,
            "preparing": 1,
            "pending": 1,
            "running": 1,
            "scheduled": 1,
            "success": 1,
        }
    )

    assert pipeline.in_progress_job_count == 6


def test_failed_jobs_are_split_by_whether_they_block_the_pipeline():
    pipeline = _pull_request_pipeline()

    assert [job.name for job in pipeline.blocking_failed_jobs] == ["blocking-one"]
    assert [job.name for job in pipeline.allowed_failed_jobs] == ["allowed-one"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("running", True), ("pending", True), ("success", False), ("failed", False)],
)
def test_is_running(status, expected):
    assert _pull_request_pipeline(root=_pipeline(status=status)).is_running is expected
