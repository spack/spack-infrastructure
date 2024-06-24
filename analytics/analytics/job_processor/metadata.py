import functools
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from dateutil.parser import isoparse
from django.conf import settings
from gitlab.v4.objects import ProjectJob

from analytics.job_processor.artifacts import get_job_artifacts_data
from analytics.job_processor.prometheus import PrometheusClient


@dataclass
class PackageInfo:
    name: str
    hash: str
    version: str
    compiler_name: str
    compiler_version: str
    arch: str
    variants: str


@dataclass
class JobMiscInfo:
    job_size: str
    stack: str
    build_jobs: int | None


@dataclass
class PodInfo:
    name: str
    node_occupancy: float
    cpu_usage_seconds: float
    max_memory: int
    avg_memory: float
    cpu_request: float | None = None
    cpu_limit: float | None = None
    memory_request: float | None = None
    memory_limit: float | None = None


@dataclass(frozen=True)
class MissingPodInfo:
    """This data doesn't exist, and so all fields are None."""

    name = None
    node_occupancy = None
    cpu_usage_seconds = None
    max_memory = None
    avg_memory = None
    cpu_request = None
    cpu_limit = None
    memory_request = None
    memory_limit = None


@dataclass
class NodeInfo:
    name: str
    system_uuid: uuid.UUID
    cpu: int
    memory: int
    capacity_type: str
    instance_type: str
    spot_price: float


@dataclass(frozen=True)
class MissingNodeInfo:
    """This data doesn't exist, and so all fields are None."""

    name = None
    system_uuid = None
    cpu = None
    memory = None
    capacity_type = None
    instance_type = None
    spot_price = None


@dataclass
class ClusterJobInfo:
    """Info about a job that ran in the cluster."""

    package: PackageInfo
    misc: JobMiscInfo
    pod: PodInfo
    node: NodeInfo


@dataclass
class NonClusterJobInfo:
    """This is a subset of information from JobInfo, where pod and node data are not present."""

    package: PackageInfo
    misc: JobMiscInfo
    pod: MissingPodInfo = field(default_factory=MissingPodInfo)
    node: MissingNodeInfo = field(default_factory=MissingNodeInfo)


# Type alias to define the union of these two types
JobInfo = ClusterJobInfo | NonClusterJobInfo


@functools.lru_cache(maxsize=128, typed=True)
def retrieve_job_info(gljob: ProjectJob) -> JobInfo:
    """Retrieve job info for a job.

    This is cached as it may be invoked by different functions to retrieve the same underlying data.
    """
    client = PrometheusClient(settings.PROMETHEUS_URL)
    pod_name = client.get_pod_name_from_gitlab_job(gljob=gljob)
    if pod_name is None:
        artifacts = get_job_artifacts_data(gljob)
        return NonClusterJobInfo(
            package=PackageInfo(
                name=artifacts.package_name,
                hash=artifacts.package_hash,
                version=artifacts.package_version,
                compiler_name=artifacts.compiler_name,
                compiler_version=artifacts.compiler_version,
                arch=artifacts.arch,
                variants=artifacts.package_variants,
            ),
            misc=JobMiscInfo(
                job_size=artifacts.job_size,
                stack=artifacts.stack,
                build_jobs=artifacts.build_jobs,
            ),
        )

    # Retrieve the remaining info from prometheus
    start = isoparse(gljob.started_at)
    end = isoparse(gljob.started_at) + timedelta(seconds=gljob.duration)
    pod_labels = client.get_pod_labels(pod=pod_name, start=start, end=end)
    requests_and_limits = client.get_pod_resource_requests_and_limits(
        pod=pod_name, start=start, end=end
    )
    node_data = client.get_pod_node_data(pod=pod_name, start=start, end=end)
    resource_usage = client.get_pod_usage_and_occupancy(
        pod=pod_name, node=node_data.name, start=start, end=end
    )

    return ClusterJobInfo(
        package=PackageInfo(
            name=pod_labels.package_name,
            hash=pod_labels.package_hash,
            version=pod_labels.package_version,
            compiler_name=pod_labels.compiler_name,
            compiler_version=pod_labels.compiler_version,
            arch=pod_labels.arch,
            variants=pod_labels.package_variants,
        ),
        misc=JobMiscInfo(
            job_size=pod_labels.job_size,
            stack=pod_labels.stack,
            build_jobs=pod_labels.build_jobs,
        ),
        pod=PodInfo(
            name=pod_name,
            node_occupancy=resource_usage.node_occupancy,
            cpu_usage_seconds=resource_usage.cpu_usage_seconds,
            max_memory=resource_usage.max_memory,
            avg_memory=resource_usage.avg_memory,
            cpu_request=requests_and_limits.cpu_request,
            cpu_limit=requests_and_limits.cpu_limit,
            memory_request=requests_and_limits.memory_request,
            memory_limit=requests_and_limits.memory_limit,
        ),
        node=NodeInfo(
            name=node_data.name,
            system_uuid=node_data.system_uuid,
            cpu=node_data.cpu,
            memory=node_data.memory,
            capacity_type=node_data.capacity_type,
            instance_type=node_data.instance_type,
            spot_price=node_data.spot_price,
        ),
    )
