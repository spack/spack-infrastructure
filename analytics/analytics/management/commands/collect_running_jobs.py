from dataclasses import dataclass
from typing import Literal

import djclick as click
import kubernetes
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.utils.quantity import parse_quantity

from analytics.models import Job

# Ensure kubernetes API is setup
kubernetes.config.load_incluster_config()


@dataclass
class PodMetadata:
    project_id: str
    job_id: str
    job_name: str
    job_started_at: str
    job_size: str
    job_ref: str
    package_name: str
    cpu_request: float
    memory_request: int
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
        (x.env for x in pod_dict["spec"]["containers"] if x.name == "build"),
        None,
    )
    if pod_env is None:
        raise Exception(
            f"Build container not found on pod {pod_dict['metadata']['name']}"
        )

    # Convert pod_env to a dictionary mapping keys to values
    pod_env = {var["name"]: var["value"] for var in pod_env}

    # Retrieve labels
    labels: dict = pod_dict["metadata"]["labels"]

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
        cpu_request=float(parse_quantity(pod_env["KUBERNETES_CPU_REQUEST"])),
        memory_request=int(parse_quantity(pod_env["KUBERNETES_MEMORY_REQUEST"])),
        package_version=labels["metrics/spack_job_spec_pkg_version"],
        compiler_name=labels["metrics/spack_job_spec_compiler_name"],
        compiler_version=labels["metrics/spack_job_spec_compiler_version"],
        arch=labels["metrics/spack_job_spec_arch"],
        package_variants=labels["metrics/spack_job_spec_variants"],
        stack=labels["metrics/spack_ci_stack_name"],
        # This var isn't guaranteed to be present
        build_jobs=pod_env.get("SPACK_BUILD_JOBS"),
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


def get_running_build_pods():
    """Returns pod running in the `pipeline` namespace that are on a valid stage, not `generate`."""
    client = kubernetes.client.CoreV1Api()
    return [
        pod
        for pod in client.list_namespaced_pod(namespace="pipeline").items
        if pod.metadata.labels["metrics/gitlab_ci_job_stage"].startswith("stage-")
    ]


def get_running_job_metadata() -> list[JobMetadata]:
    client = kubernetes.client.CoreV1Api()
    pods = get_running_build_pods()
    node_map = {
        node.metadata.name: node.to_dict()
        for node in client.list_node(label_selector="spack.io/pipeline=true").items
    }

    results = []
    for pod in pods:
        node = node_map[pod.to_dict()["spec"]["node_name"]]
        results.append(
            JobMetadata(
                node=get_node_metadata(node),
                pod=get_pod_metadata(pod),
            )
        )

    return results


@click.command()
def main():
    job_metadata = get_running_job_metadata()

    # Ensure we only act on new jobs
    running_job_ids = [x.pod.job_id for x in job_metadata]
    existing_job_ids = set(
        Job.objects.filter(job_id__in=running_job_ids).values_list("job_id", flat=True)
    )
    new_jobs = [job for job in job_metadata if job.pod.job_id not in existing_job_ids]

    # Bulk create new jobs
    Job.objects.bulk_create(
        [
            # Tags, duration intentionally left blank, as they will be updated once the job finishes
            Job(
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
            for item in new_jobs
        ]
    )


if __name__ == "__main__":
    main()
