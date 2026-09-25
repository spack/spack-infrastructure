import pytest

from analytics.pipeline_status.templatetags.pipeline_status_extras import (
    duration,
    humanize_status,
    status_badge_class,
)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "—"),
        (-1, "—"),
        (0, "0s"),
        (45, "45s"),
        (60, "1m 00s"),
        (725, "12m 05s"),
        (3600, "1h 00m"),
        (7620, "2h 07m"),
        (4470.9, "1h 14m"),
    ],
)
def test_duration_formats_compactly(seconds, expected):
    assert duration(seconds) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("success", "badge-success"),
        ("failed", "badge-error"),
        ("running", "badge-info"),
        ("pending", "badge-warning"),
        ("canceled", "badge-neutral"),
        ("skipped", "badge-ghost"),
        # An unrecognised state still has to render as a badge.
        ("some_new_gitlab_state", "badge-neutral"),
        (None, "badge-neutral"),
    ],
)
def test_status_badge_class(status, expected):
    assert status_badge_class(status) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("failed", "Failed"),
        ("waiting_for_resource", "Waiting for resource"),
        ("downstream_pipeline_creation_failed", "Downstream pipeline creation failed"),
        (None, "Unknown"),
        ("", "Unknown"),
    ],
)
def test_humanize_status(status, expected):
    assert humanize_status(status) == expected
