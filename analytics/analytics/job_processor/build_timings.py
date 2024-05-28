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


def get_phase_mapping(timings: list[dict]) -> dict[str, TimerPhaseDimension]:
    phases: set[tuple[str, bool]] = set()
    for entry in timings:
        phases |= {(phase["path"], ("/" in phase["path"])) for phase in entry["phases"]}

    TimerPhaseDimension.objects.bulk_create(
        [
            TimerPhaseDimension(path=path, is_subphase=is_subphase)
            for path, is_subphase in phases
        ],
        ignore_conflicts=True,
    )

    paths = [p[0] for p in phases]
    return {obj.path: obj for obj in TimerPhaseDimension.objects.filter(path__in=paths)}


def get_package_hash_mapping(timings: list[dict]) -> dict[str, PackageHashDimension]:
    hashes: set[str] = {entry["hash"] for entry in timings}
    PackageHashDimension.objects.bulk_create(
        [PackageHashDimension(hash=hash) for hash in hashes], ignore_conflicts=True
    )

    return {
        obj.hash: obj for obj in PackageHashDimension.objects.filter(hash__in=hashes)
    }


def get_package_mapping(timings: list[dict]) -> dict[str, PackageDimension]:
    packages: set[str] = {entry["name"] for entry in timings}
    PackageDimension.objects.bulk_create(
        [
            PackageDimension(
                name=package_name,
                version="",
                compiler_name="",
                compiler_version="",
                arch="",
                variants="",
            )
            for package_name in packages
        ],
        ignore_conflicts=True,
    )

    return {
        obj.name: obj
        for obj in PackageDimension.objects.filter(
            name__in=packages,
            version="",
            compiler_name="",
            compiler_version="",
            arch="",
            variants="",
        )
    }


def create_build_timing_facts(job_fact: JobFact, gljob: ProjectJob) -> BuildTimingFacts:
    timings = [t for t in get_timings_json(gljob) if t.get("name") and t.get("hash")]

    package_hash_mapping = get_package_hash_mapping(timings=timings)
    package_mapping = get_package_mapping(timings=timings)
    timer_data_mapping = {obj.cache: obj for obj in TimerDataDimension.objects.all()}
    phase_mapping = get_phase_mapping(timings=timings)

    # Now that we have all the dimensions covered, go through and construct facts to bulk create
    timer_facts = []
    phase_facts = []
    for entry in timings:
        timer_data = timer_data_mapping[entry["cache"]]
        package = package_mapping[entry["name"]]
        package_hash = package_hash_mapping[entry["hash"]]
        total_time = entry["total"]
        timer_facts.append(
            TimerFact(
                job=job_fact.job,
                timer_data=timer_data,
                package=package,
                package_hash=package_hash,
                total_time=total_time,
            )
        )

        # Add all phases to bulk phase list
        for phase in entry["phases"]:
            phase_time = phase["seconds"]
            phase_facts.append(
                # TODO: Add date and time dimensions
                TimerPhaseFact(
                    # Shared with timer
                    job=job_fact.job,
                    timer_data=timer_data,
                    package=package,
                    package_hash=package_hash,
                    # For phases only
                    phase=phase_mapping[phase["path"]],
                    time=phase_time,
                    ratio_of_total=phase_time / total_time,
                )
            )

    # Bulk create all at once
    timer_facts = TimerFact.objects.bulk_create(timer_facts)
    phase_facts = TimerPhaseFact.objects.bulk_create(phase_facts)

    return (timer_facts, phase_facts)
