import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import djclick as click
import kubernetes
from django.db.utils import IntegrityError
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.utils.quantity import parse_quantity

from analytics.models import Job

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Ensure kubernetes API is setup
try:
    kubernetes.config.load_config()
except kubernetes.config.config_exception.ConfigException as e:
    logger.error("Could not load kubernetes config. Is KUBECONFIG set?")
    logger.error(f"\tExact error from kubernetes: {e}")
    exit(1)


client = kubernetes.client.CoreV1Api()


@dataclass
class PodMetadata:
    project_id: str
    job_id: str
    job_name: str
    job_started_at: str
    job_size: str
    job_ref: str
    package_name: str
    cpu_request: float | None
    memory_request: int | None
    package_version: str
    compiler_name: str
    compiler_version: str
    arch: str
    package_variants: str
    stack: str
    build_jobs: str | None = None


@dataclass
class NodeMetadata:
    name: str
    uid: str
    instance_type: str
    capacity_type: Literal["spot", "on-demand"]
    cpu: int
    mem: int


@dataclass
class JobMetadata:
    node: NodeMetadata
    pod: PodMetadata


def get_pod_metadata(pod: V1Pod) -> PodMetadata:
    """Get data from the pod that's necessary for storing a job."""
    pod_dict = pod.to_dict()
    pod_env = next(
        (x["env"] for x in pod_dict["spec"]["containers"] if x["name"] == "build"),
        None,
    )
    if pod_env is None:
        raise Exception(
            f"Build container not found on pod {pod_dict['metadata']['name']}"
        )

    # Convert pod_env to a dictionary mapping keys to values
    pod_env = {var["name"]: var["value"] for var in pod_env}

    # Retrieve labels and annotations
    labels: dict = pod_dict["metadata"]["labels"]
    annotations: dict = pod_dict["metadata"]["annotations"]

    # Retrieve k8s resource requests, if they're set
    cpu_request = pod_env.get("KUBERNETES_CPU_REQUEST")
    memory_request = pod_env.get("KUBERNETES_MEMORY_REQUEST")

    # Return data in one place
    return PodMetadata(
        project_id=pod_env["CI_PROJECT_ID"],
        job_id=labels["gitlab/ci_job_id"],
        job_name=pod_env["CI_JOB_NAME"],
        job_started_at=pod_env["CI_JOB_STARTED_AT"],
        job_size=labels["gitlab/ci_job_size"],
        job_ref=pod_env["CI_COMMIT_REF_NAME"],
        # Note: tags not provided here, will be populated in the gitlab webhook
        package_name=labels["metrics/spack_job_spec_pkg_name"],
        cpu_request=float(parse_quantity(cpu_request)) if cpu_request else None,
        memory_request=int(parse_quantity(memory_request)) if memory_request else None,
        package_version=annotations["metrics/spack_job_spec_pkg_version"],
        compiler_name=annotations["metrics/spack_job_spec_compiler_name"],
        compiler_version=annotations["metrics/spack_job_spec_compiler_version"],
        arch=annotations["metrics/spack_job_spec_arch"],
        package_variants=annotations["metrics/spack_job_spec_variants"],
        stack=labels["metrics/spack_ci_stack_name"],
        # build jobs isn't always present
        build_jobs=annotations.get("metrics/spack_job_build_jobs"),
    )


def get_node_metadata(node: dict) -> NodeMetadata:
    node_labels = node["metadata"]["labels"]

    return NodeMetadata(
        name=node["metadata"]["name"],
        uid=node["metadata"]["uid"],
        instance_type=node_labels["node.kubernetes.io/instance-type"],
        capacity_type=node_labels["karpenter.sh/capacity-type"],
        cpu=int(node_labels["karpenter.k8s.aws/instance-cpu"]),
        mem=int(node_labels["karpenter.k8s.aws/instance-memory"]),
    )


def handle_scheduled_pipeline_pod(wrapped_event: dict, start_time: datetime):
    if wrapped_event["type"] != "ADDED":
        return

    # Check that it's a current event
    event: dict = wrapped_event["object"].to_dict()
    created: datetime = event["metadata"]["creation_timestamp"]
    if created < start_time:
        logger.debug(f"Skipping event from {created.isoformat()}")
        return

    # Retrieve pod. Pod retrieval could fail for various reasons, so handle this gracefully
    pod_name = event["involved_object"]["name"]
    try:
        pod: V1Pod = client.read_namespaced_pod(namespace="pipeline", name=pod_name)  # type: ignore
    except kubernetes.client.ApiException:
        logger.warning(f'Could not retrieve pod {pod_name} in namespace "pipeline"')
        return

    # Ensure that this pod has a non-empty package name label before continuing
    labels: dict = pod.to_dict()["metadata"]["labels"]
    if labels.get("metrics/spack_job_spec_pkg_name", "") == "":
        logger.debug(f"Skipping pod with missing package name: {pod_name}")
        return

    # Retrieve node
    node_name = pod.to_dict()["spec"]["node_name"]
    node = client.read_node(name=node_name).to_dict()  # type: ignore
    item = JobMetadata(
        node=get_node_metadata(node),
        pod=get_pod_metadata(pod),
    )

    # Check to make sure job hasn't already been recorded
    if Job.objects.filter(
        project_id=item.pod.project_id, job_id=item.pod.job_id
    ).exists():
        return

    # Tags, duration intentionally left blank, as they will be updated once the job finishes
    try:
        job = Job.objects.create(
            # Core data
            job_id=item.pod.job_id,
            project_id=item.pod.project_id,
            name=item.pod.job_name,
            started_at=item.pod.job_started_at,
            duration=None,
            ref=item.pod.job_ref,
            package_name=item.pod.package_name,
            job_cpu_request=item.pod.cpu_request,
            job_memory_request=item.pod.memory_request,
            # Node data
            node_name=item.node.name,
            node_uid=item.node.uid,
            node_instance_type=item.node.instance_type,
            node_capacity_type=item.node.capacity_type,
            node_cpu=item.node.cpu,
            node_mem=item.node.mem,
            # Extra data
            package_version=item.pod.package_version,
            compiler_name=item.pod.compiler_name,
            compiler_version=item.pod.compiler_version,
            arch=item.pod.arch,
            package_variants=item.pod.package_variants,
            build_jobs=item.pod.build_jobs,
            job_size=item.pod.job_size,
            stack=item.pod.stack,
            # By defninition this is true, since this script runs in the cluster
            aws=True,
        )
    except IntegrityError as e:
        logger.error(
            f"Could not create Job with job_id {item.pod.job_id}. This may indicate a race "
            "condition. The error is logged below."
        )
        logger.error(e)
        return

    logger.info(f"Processed job {job.job_id}")


@click.command()
def main():
    start_time = datetime.now(timezone.utc)

    # Setup event stream
    watcher = kubernetes.watch.Watch()
    events = watcher.stream(
        client.list_namespaced_event,
        namespace="pipeline",
        field_selector="reason=Scheduled,involvedObject.kind=Pod",
    )

    logger.info("Listening for scheduled pipeline pods...")
    logger.info(f"Start time is {start_time.isoformat()}")
    logger.info("----------------------------------------")

    # Get events yielded from generator
    for event in events:
        assert isinstance(event, dict)
        handle_scheduled_pipeline_pod(event, start_time)


if __name__ == "__main__":
    main()
