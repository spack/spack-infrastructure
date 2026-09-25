"""Presentation helpers for the pipeline status templates."""

from django import template

register = template.Library()

# Map GitLab's job/pipeline states onto DaisyUI badge modifiers. Keys are the full set
# of states in GitLab's CommitStatus enum; anything unrecognised falls back to neutral
# rather than rendering an unstyled badge.
_STATUS_BADGE_CLASSES = {
    "success": "badge-success",
    "failed": "badge-error",
    "running": "badge-info",
    "created": "badge-warning",
    "waiting_for_resource": "badge-warning",
    "preparing": "badge-warning",
    "pending": "badge-warning",
    "scheduled": "badge-warning",
    "canceled": "badge-neutral",
    "canceling": "badge-neutral",
    "skipped": "badge-ghost",
    "manual": "badge-ghost",
}


@register.filter
def status_badge_class(status: str | None) -> str:
    return _STATUS_BADGE_CLASSES.get(status or "", "badge-neutral")


@register.filter
def humanize_status(status: str | None) -> str:
    """ "waiting_for_resource" -> "Waiting for resource"."""
    if not status:
        return "Unknown"

    return status.replace("_", " ").capitalize()


@register.filter
def duration(seconds: int | float | None) -> str:
    """Format a duration in seconds compactly, e.g. "45s", "12m 04s", "2h 07m".

    Durations on this page span single-second jobs to multi-hour pipelines, so the
    units shown adapt rather than always rendering hours.
    """
    if seconds is None:
        return "—"

    total = int(seconds)
    if total < 0:
        return "—"

    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"

    return f"{total}s"
