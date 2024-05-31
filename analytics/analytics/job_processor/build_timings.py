import json

import spack.spec
import spack.traverse
from gitlab.v4.objects import ProjectJob

from analytics.core.models.dimensions import (
    PackageDimension,
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


def get_spec_json(job: ProjectJob) -> list[dict]:
    repro_dir_prefix = "jobs_scratch_dir/reproduction"
    with get_job_artifacts_file(job, f"{repro_dir_prefix}/repro.json") as file:
        repro = json.load(file)

    spec_filename = repro["job_spec_json"]
    spec_file = f"{repro_dir_prefix}/{spec_filename}"
    with get_job_artifacts_file(job, spec_file) as file:
        spec = json.load(file)

    return spec["spec"]["nodes"]


def create_spec_packages(job: ProjectJob):
    spec = get_spec_json(job=job)
    root_spec = spack.spec.Spec.from_dict(spec)

    # Construct a list of specs to create by going through each node and pulling out the relevant info
    packages = []
    for node in spack.traverse.traverse_nodes([root_spec], depth=False):  # type: ignore
        node: spack.spec.Spec

        packages.append(
            PackageDimension(
                name=node.name,
                hash=node.dag_hash(),
                version=node.version.string,
                compiler_name=node.format("{compiler.name}"),
                compiler_version=node.format("{compiler.version}"),
                arch=node.format("{arch}"),
                variants=node.format("{variants}"),
            )
        )

    # Bulk create
    PackageDimension.objects.bulk_create(packages, ignore_conflicts=True)


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


def get_package_mapping(timings: list[dict]) -> dict[str, PackageDimension]:
    hashes: set[str] = {entry["hash"] for entry in timings}
    return {obj.hash: obj for obj in PackageDimension.objects.filter(hash__in=hashes)}


def create_build_timing_facts(job_fact: JobFact, gljob: ProjectJob) -> BuildTimingFacts:
    timings = [t for t in get_timings_json(gljob) if t.get("name") and t.get("hash")]

    # First, ensure that all specs are entered into the db. Then, fetch all timing packages
    create_spec_packages(gljob)
    package_mapping = get_package_mapping(timings=timings)

    timer_data_mapping = {obj.cache: obj for obj in TimerDataDimension.objects.all()}
    phase_mapping = get_phase_mapping(timings=timings)

    # Now that we have all the dimensions covered, go through and construct facts to bulk create
    timer_facts = []
    phase_facts = []
    for entry in timings:
        timer_data = timer_data_mapping[entry["cache"]]
        package = package_mapping[entry["hash"]]
        total_time = entry["total"]
        timer_facts.append(
            TimerFact(
                job=job_fact.job,
                date=job_fact.start_date,
                time=job_fact.start_time,
                timer_data=timer_data,
                package=package,
                total_duration=total_time,
            )
        )

        # Add all phases to bulk phase list
        for phase in entry["phases"]:
            phase_time = phase["seconds"]
            phase_facts.append(
                TimerPhaseFact(
                    # Shared with timer
                    job=job_fact.job,
                    date=job_fact.start_date,
                    time=job_fact.start_time,
                    timer_data=timer_data,
                    package=package,
                    # For phases only
                    phase=phase_mapping[phase["path"]],
                    duration=phase_time,
                    ratio_of_total=phase_time / total_time,
                )
            )

    # Bulk create all at once
    timer_facts = TimerFact.objects.bulk_create(timer_facts)
    phase_facts = TimerPhaseFact.objects.bulk_create(phase_facts)

    return (timer_facts, phase_facts)
