import pytest

from analytics.job_processor.dimensions import _assign_error_taxonomy

FAILED_JOB = {"build_status": "failed", "build_failure_reason": "unknown_failure_reason"}


@pytest.mark.parametrize(
    "trace,expected_class",
    [
        # Single match
        ("socket.timeout", "network_timeout"),
        ("error found in build log:", "build_error"),
        ("No space left on device", "no_space"),
        # No match → other
        ("everything went fine", "other"),
        # Deconfliction: setup_env (higher priority) beats file_not_found (lower).
        # "setup-env.sh: No such file or directory" satisfies both patterns.
        (
            "setup-env.sh: No such file or directory",
            "setup_env",
        ),
        # Deconfliction: build_error (higher priority) beats spack_error (lower).
        (
            "error found in build log:\nTo reproduce this build locally, run:",
            "build_error",
        ),
        # Deconfliction: no_space (higher priority) beats file_not_found (lower).
        # Both patterns match "No space left on device\nNo such file or directory".
        (
            "No space left on device\nNo such file or directory",
            "no_space",
        ),
        # Deconfliction: dns_error (higher priority) beats network_error (lower).
        # dns_error: "could not resolve host"; network_error: "curl: (6) Could not resolve host"
        # A trace with both patterns present should resolve to dns_error.
        (
            "could not resolve host\ncurl: (6) Could not resolve host",
            "dns_error",
        ),
    ],
)
def test_deconfliction_order(trace, expected_class):
    error_class, _ = _assign_error_taxonomy(FAILED_JOB, trace)
    assert error_class == expected_class


@pytest.mark.parametrize(
    "build_failure_reason,expected_class",
    [
        ("stuck_or_timeout_failure", "stuck_or_timeout_failure"),
        ("scheduler_failure", "scheduler_failure"),
    ],
)
def test_special_classes_assigned_via_build_failure_reason(
    build_failure_reason, expected_class
):
    job = {"build_status": "failed", "build_failure_reason": build_failure_reason}
    error_class, _ = _assign_error_taxonomy(job, "")
    assert error_class == expected_class
