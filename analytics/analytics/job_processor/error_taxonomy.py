import re
from pathlib import Path
from typing import Any

import yaml


def _assign_error_taxonomy(job_input_data: dict[str, Any], job_trace: str):
    if job_input_data["build_status"] != "failed":
        raise ValueError("This function should only be called for failed jobs")

    with open(Path(__file__).parent / "error_taxonomy.yaml") as f:
        taxonomy = yaml.load(f, Loader=yaml.CSafeLoader)["taxonomy"]

    error_taxonomy_version = taxonomy["version"]

    # Compile matching patterns from job trace
    matching_patterns = set()
    for entry in taxonomy["error_classes"]:
        for grep_expr in entry.get("grep_for") or []:
            if re.compile(grep_expr).search(job_trace):
                matching_patterns.add(entry["name"])
                break

    # If the job logs matched any regexes, assign it the taxonomy
    # with the highest priority (first entry in the ordered list wins).
    # Otherwise, assign it a taxonomy of "other".
    job_error_class = None
    if len(matching_patterns):
        for entry in taxonomy["error_classes"]:
            if entry["name"] in matching_patterns:
                job_error_class = entry["name"]
                break
    else:
        job_error_class = "other"

        # If this job timed out or failed to be scheduled by GitLab,
        # label it as such.
        if job_input_data["build_failure_reason"] in (
            "stuck_or_timeout_failure",
            "scheduler_failure",
        ):
            job_error_class = job_input_data["build_failure_reason"]

    return job_error_class, error_taxonomy_version
