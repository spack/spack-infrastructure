import json

from gitlab.v4.objects import ProjectJob

from analytics.job_processor.artifacts import get_job_artifacts_file
from analytics.core.models import Job, Timer, TimerPhase


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
