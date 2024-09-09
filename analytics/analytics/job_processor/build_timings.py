import json

from gitlab.v4.objects import ProjectJob

from analytics.core.models.dimensions import (
    PackageDimension,
    PackageSpecDimension,
    TimerDataDimension,
    TimerPhaseDimension,
)
from analytics.core.models.facts import JobFact, TimerFact, TimerPhaseFact
from analytics.job_processor.artifacts import (
    JobArtifactFileNotFound,
    get_job_artifacts_file,
)


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

    return spec


def create_packages_and_specs(job: ProjectJob):
    import spack.spec
    import spack.traverse

    spec = get_spec_json(job=job)
    root_spec = spack.spec.Spec.from_dict(spec)

    # Construct a list of specs to create by going through each node and pulling out the relevant info
    package_names = set()
    specs = []
    for node in spack.traverse.traverse_nodes([root_spec], depth=False):  # type: ignore
        node: spack.spec.Spec

        package_names.add(node.name)
        specs.append(
            PackageSpecDimension(
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
    PackageSpecDimension.objects.bulk_create(specs, ignore_conflicts=True)
    PackageDimension.objects.bulk_create(
        [PackageDimension(name=name) for name in package_names], ignore_conflicts=True
    )


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


def get_package_spec_mapping(timings: list[dict]) -> dict[str, PackageSpecDimension]:
    hashes: set[str] = {entry["hash"] for entry in timings}
    return {
        obj.hash: obj for obj in PackageSpecDimension.objects.filter(hash__in=hashes)
    }


def get_package_mapping(timings: list[dict]) -> dict[str, PackageDimension]:
    names: set[str] = {entry["name"] for entry in timings}
    return {obj.name: obj for obj in PackageDimension.objects.filter(name__in=names)}


def create_build_timing_facts(job_fact: JobFact, gljob: ProjectJob):
    # Sometimes the timings file isn't present, even on successful jobs.
    # If that's the case, we just skip this step.
    try:
        data = get_timings_json(gljob)
        timings = [t for t in data if t.get("name") and t.get("hash")]
    except JobArtifactFileNotFound:
        return

    # First, ensure that all packages and specs are entered into the db. Then, fetch all timing packages
    create_packages_and_specs(gljob)
    package_mapping = get_package_mapping(timings=timings)
    package_spec_mapping = get_package_spec_mapping(timings=timings)

    timer_data_mapping = {obj.cache: obj for obj in TimerDataDimension.objects.all()}
    phase_mapping = get_phase_mapping(timings=timings)

    # Now that we have all the dimensions covered, go through and construct facts to bulk create
    timer_facts = []
    phase_facts = []
    for entry in timings:
        timer_data = timer_data_mapping[entry["cache"]]
        package = package_mapping[entry["name"]]
        spec = package_spec_mapping[entry["hash"]]
        total_time = entry["total"]
        timer_facts.append(
            TimerFact(
                job=job_fact.job,
                date=job_fact.start_date,
                time=job_fact.start_time,
                timer_data=timer_data,
                package=package,
                spec=spec,
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
                    spec=spec,
                    # For phases only
                    phase=phase_mapping[phase["path"]],
                    duration=phase_time,
                    ratio_of_total=phase_time / total_time,
                )
            )

    # Bulk create all at once
    timer_facts = TimerFact.objects.bulk_create(timer_facts, ignore_conflicts=True)
    phase_facts = TimerPhaseFact.objects.bulk_create(phase_facts, ignore_conflicts=True)
