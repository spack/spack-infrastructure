import datetime
import uuid

import djclick as click
from django.db import IntegrityError
from tqdm import tqdm

from analytics.core.models import (
    DateDimension,
    JobDataDimension,
    JobFact,
    LegacyJob,
    LegacyJobAttempt,
    LegacyJobPod,
    LegacyNode,
    NodeCapacityType,
    NodeDimension,
    PackageDimension,
    RunnerDimension,
    TimeDimension,
)


def create_all_times():
    for sec in range(86400):
        h = sec // 3600
        m = (sec // 60) % 60
        s = sec % 60
        t = datetime.time(hour=h, minute=m, second=s)
        try:
            TimeDimension.objects.create(
                time_key=int(t.strftime("%H%M%S")),
                time=t,
                am_or_pm="AM" if t.hour < 12 else "PM",
                hour_12=int(t.strftime("%I")),
                hour_24=t.hour,
                minute=t.minute,
                minute_of_day=t.hour * 60 + t.minute,
                second=t.second,
                second_of_hour=t.minute * 60 + t.second,
                second_of_day=t.hour * 60 * 60 + t.minute * 60 + t.second,
            )
        except IntegrityError:
            pass


def get_related_attr(obj: LegacyNode | LegacyJobPod | None, field: str):
    if obj is None:
        return None

    return getattr(obj, field)


def get_or_create_date_row(date: datetime.date):
    d = date
    existing = DateDimension.objects.filter(date=d).first()
    if existing:
        return existing

    return DateDimension.objects.create(
        date_key=int(d.strftime("%Y%m%d")),
        date=d,
        date_description=d.strftime("%B %d, %Y"),
        day_of_week=d.weekday() + 1,
        day_of_month=d.day,
        day_of_year=d.toordinal() - datetime.date(d.year, 1, 1).toordinal() + 1,
        day_name=d.strftime("%A"),
        weekday=d.weekday() in [5, 6],
        month=d.month,
        month_name=d.strftime("%B"),
        quarter=(d.month - 1) // 3 + 1,
        year=d.year,
    )


def get_or_create_time_row(time: datetime.time):
    # Strip time to second precision
    t = time.replace(microsecond=0)

    existing = TimeDimension.objects.filter(time=t).first()
    if existing:
        return existing

    return TimeDimension.objects.create(
        time_key=int(t.strftime("%H%M%S")),
        time=t,
        am_or_pm="AM" if t.hour < 12 else "PM",
        hour_12=int(t.strftime("%I")),
        hour_24=t.hour,
        minute=t.minute,
        minute_of_day=t.hour * 60 + t.minute,
        second=t.second,
        second_of_hour=t.minute * 60 + t.second,
        second_of_day=t.hour * 60 * 60 + t.minute * 60 + t.second,
    )


@click.command()
def migrate_data():
    # Create empty node
    if not NodeDimension.objects.filter(name="").exists():
        NodeDimension.objects.create(
            name="",
            system_uuid=uuid.uuid4(),
            cpu=0,
            memory=0,
            capacity_type=NodeCapacityType.SPOT,
            instance_type="",
        )

    # Run through existing jobs and place data in new models
    jobs = LegacyJob.objects.select_related("node", "pod").all()

    # for job in tqdm(jobs.iterator(), total=jobs.count()):
    for job in tqdm(jobs):
        if JobDataDimension.objects.filter(job_id=job.job_id).exists():
            continue

        start_date = get_or_create_date_row(job.started_at.date())
        start_time = get_or_create_time_row(job.started_at.time())
        end_date = get_or_create_date_row(job.finished_at.date())
        end_time = get_or_create_time_row(job.finished_at.time())

        # Create node link
        if job.node is None:
            node = NodeDimension.objects.get(name="")
        else:
            node, _ = NodeDimension.objects.get_or_create(
                system_uuid=job.node.system_uuid,
                name=job.node.name,
                cpu=job.node.cpu,
                memory=job.node.memory,
                capacity_type=job.node.capacity_type,
                instance_type=job.node.instance_type,
            )

        # Create runner link
        # TODO: Since we don't really have this data atm, for now it's empty
        runner, _ = RunnerDimension.objects.get_or_create(
            runner_id=0, name="", platform="", host="", metal=False
        )

        # Check if package name has version
        if "@" in job.package_name:
            package_name, package_version = job.package_name.split("@")
        else:
            package_name = job.package_name
            package_version = job.package_version

        # Create package link
        package, _ = PackageDimension.objects.get_or_create(
            name=package_name,
            version=package_version,
            compiler_name=job.compiler_name,
            compiler_version=job.compiler_version,
            arch=job.arch,
            variants=job.package_variants or "",
        )

        # Get potential data from job_attempt model
        job_attempt = LegacyJobAttempt.objects.filter(job_id=job.job_id).first()
        if job_attempt is None:
            is_retry = False
            is_manual_retry = False
            attempt_number = 1
            final_attempt = False
            status = "success"
            error_taxonomy = None
        else:
            is_retry = job_attempt.is_retry
            is_manual_retry = job_attempt.is_manual_retry
            attempt_number = job_attempt.attempt_number
            final_attempt = job_attempt.final_attempt
            status = job_attempt.status
            error_taxonomy = job_attempt.error_taxonomy

        # Create job data link
        job_data, _ = JobDataDimension.objects.get_or_create(
            job_id=job.job_id,
            project_id=job.project_id,
            commit_id=0,
            job_url="https://spack.io",
            name=job.name,
            ref=job.ref,
            tags=job.tags,
            job_size=job.job_size,
            stack=job.stack,
            is_retry=is_retry,
            is_manual_retry=is_manual_retry,
            attempt_number=attempt_number,
            final_attempt=final_attempt,
            status=status,
            error_taxonomy=error_taxonomy,
            unnecessary=job.unnecessary,
            pod_name=job.pod.name if job.pod else None,
            gitlab_runner_version="",
            is_build=True,
        )

        existing = JobFact.objects.filter(
            start_date=start_date,
            start_time=start_time,
            end_date=end_date,
            end_time=end_time,
            node=node,
            runner=runner,
            package=package,
            job=job_data,
        ).first()
        if existing:
            continue

        # Calculate any derived fields
        job_cost = None
        if job.pod is not None and job.node is not None:
            job_cost = (
                job.duration.total_seconds()
                * job.pod.node_occupancy
                * (float(job.node.instance_type_spot_price) / 3600)
            )

        node_spot_price = get_related_attr(job.node, "instance_type_spot_price")
        node_price_per_second = (
            node_spot_price / 3600 if node_spot_price is not None else None
        )

        # Now populate numeric fields
        JobFact.objects.create(
            start_date=start_date,
            start_time=start_time,
            end_date=end_date,
            end_time=end_time,
            node=node,
            runner=runner,
            package=package,
            job=job_data,
            # numeric
            duration=job.duration,
            duration_seconds=job.duration.total_seconds(),
            cost=job_cost,
            build_jobs=int(job.build_jobs) if job.build_jobs else None,
            pod_node_occupancy=get_related_attr(job.pod, "node_occupancy"),
            pod_cpu_usage_seconds=get_related_attr(job.pod, "cpu_usage_seconds"),
            pod_max_mem=get_related_attr(job.pod, "max_mem"),
            pod_avg_mem=get_related_attr(job.pod, "avg_mem"),
            node_price_per_second=node_price_per_second,
            node_cpu=get_related_attr(job.node, "cpu"),
            node_memory=get_related_attr(job.node, "memory"),
            pod_cpu_request=get_related_attr(job.pod, "cpu_request"),
            pod_cpu_limit=get_related_attr(job.pod, "cpu_limit"),
            pod_memory_request=get_related_attr(job.pod, "memory_request"),
            pod_memory_limit=get_related_attr(job.pod, "memory_limit"),
        )
