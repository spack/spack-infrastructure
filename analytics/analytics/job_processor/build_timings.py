import json
import tempfile
import zipfile
from contextlib import contextmanager

from gitlab.v4.objects import ProjectJob

from analytics.models import Job, Timer, TimerPhase


class JobArtifactFileNotFound(Exception):
    def __init__(self, job: ProjectJob, filename: str):
        message = f"File {filename} not found in job artifacts of job {job.id}"
        super().__init__(message)


@contextmanager
def get_job_artifacts_file(job: ProjectJob, filename: str):
    """Yields a file IO, raises KeyError if the filename is not present"""
    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
        artifacts_file = temp.name
        with open(artifacts_file, "wb") as f:
            job.artifacts(streamed=True, action=f.write)

        with zipfile.ZipFile(artifacts_file) as zfile:
            try:
                with zfile.open(filename) as timing_file:
                    yield timing_file
            except KeyError:
                raise JobArtifactFileNotFound(job, filename)


def get_timings_json(job: ProjectJob) -> list[dict]:
    timing_filename = "jobs_scratch_dir/user_data/install_times.json"
    with get_job_artifacts_file(job, timing_filename) as file:
        return json.load(file)


def create_build_timings(job: Job, gl_job: ProjectJob):
    timings = get_timings_json(gl_job)

    # Iterate through each timer and create timers and phase results
    phases = []
    for entry in timings:
        # Sometimes name can be missing, skip if so
        name = entry.get("name")
        if name is None:
            continue

        # Check for timer and skip if already exists
        pkghash = entry.get("hash")
        if Timer.objects.filter(job=job, name=name, hash=pkghash).exists():
            continue

        # Create timer
        timer = Timer.objects.create(
            job=job,
            name=name,
            hash=pkghash,
            cache=entry["cache"],
            time_total=entry["total"],
        )

        # Add all phases to bulk phase list
        phases.extend(
            [
                TimerPhase(
                    timer=timer,
                    name=phase["name"],
                    path=phase["path"],
                    seconds=phase["seconds"],
                    count=phase["count"],
                    is_subphase=("/" in phase["path"]),
                )
                for phase in entry["phases"]
            ]
        )

    # Bulk create phases
    TimerPhase.objects.bulk_create(phases)
