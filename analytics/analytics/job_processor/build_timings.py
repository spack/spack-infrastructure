import json

from gitlab.v4.objects import ProjectJob

from analytics.core.models.dimensions import (
    PackageDimension,
    PackageHashDimension,
    TimerDataDimension,
    TimerPhaseDimension,
)
from analytics.core.models.facts import JobFact, TimerFact, TimerPhaseFact
from analytics.job_processor.artifacts import get_job_artifacts_file

BuildTimingFacts = tuple[list[TimerFact], list[TimerPhaseFact]]


def get_timings_json(job: ProjectJob) -> list[dict]:
    timing_filename = "jobs_scratch_dir/user_data/install_times.json"
    with get_job_artifacts_file(job, timing_filename) as file:
        return json.load(file)


def create_build_timing_facts(job_fact: JobFact, gljob: ProjectJob) -> BuildTimingFacts:
    timings = get_timings_json(gljob)

    # Iterate through each timer and create timers and phase results
    timer_facts = []
    phase_facts = []
    for entry in timings:
        # Sometimes name can be missing, skip if so
        package_name = entry.get("name")
        phash = entry.get("hash")
        if package_name is None or phash is None:
            continue

        # Create dimensions
        timer_data = TimerDataDimension.objects.get(cache=entry["cache"])
        package_hash, _ = PackageHashDimension.objects.get_or_create(hash=phash)
        package, _ = PackageDimension.objects.get_or_create(
            name=package_name,
            version="",
            compiler_name="",
            compiler_version="",
            arch="",
            variants="",
        )

        # Create timer
        total_time = entry["total"]
        timer_fact, _ = TimerFact.objects.get_or_create(
            job=job_fact.job,
            timer_data=timer_data,
            package=package,
            package_hash=package_hash,
            total_time=total_time,
        )
        timer_facts.append(timer_fact)

        # Add all phases to bulk phase list
        for phase_entry in entry["phases"]:
            phase, _ = TimerPhaseDimension.objects.get_or_create(
                path=phase_entry["path"], is_subphase=("/" in phase_entry["path"])
            )

            # TODO: Add date and time dimensions
            phase_time = phase["seconds"]
            phase_fact, _ = TimerPhaseFact.objects.get_or_create(
                job=job_fact.job,
                timer_data=timer_data,
                phase=phase,
                package=package,
                package_hash=package_hash,
                time=phase_time,
                ratio_of_total=phase_time / total_time,
            )
            phase_facts.append(phase_fact)

    return (timer_facts, phase_facts)
