import math
from datetime import datetime
from urllib.parse import urlencode

import requests
from kubernetes.utils.quantity import parse_quantity

from analytics.models import Job

CLUSTER_INTERNAL_PROMETHEUS_URL = (
    "kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
)
PROM_MAX_RESOLUTION = 10_000


class PrometheusClient:
    def __init__(self, url: str | None = None) -> None:
        if url is None:
            url = CLUSTER_INTERNAL_PROMETHEUS_URL

        self.api_url = f"{url.rstrip('/')}/api/v1"

    def query_single(self, query: str, time: datetime):
        params = {
            "query": query,
            "time": time.timestamp(),
        }

        query_params = urlencode(params)
        query_url = f"http://{self.api_url}/query?{query_params}"
        res = requests.get(query_url)
        res.raise_for_status()

        return res.json()["data"]["result"]

    def query_range(self, query: str, start: datetime, end: datetime):
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": math.ceil(
                (end.timestamp() - start.timestamp()) / PROM_MAX_RESOLUTION
            ),
        }
        query_params = urlencode(params)
        query_url = f"http://{self.api_url}/query_range?{query_params}"
        res = requests.get(query_url)
        res.raise_for_status()

        return res.json()["data"]["result"]


def annotate_job_resource_requests_and_limits(
    job: Job,
    pod: str,
    client: PrometheusClient,
    time: datetime,
):
    """Annotate cpu and memory resource requests and limits."""

    def extract_value(result: dict | None) -> int | float | None:
        if result is None:
            return None

        num = float(result["value"][1])
        if num.is_integer():
            num = int(num)

        return num

    # list where one entry is cpu, the other is mem
    resource_requests = client.query_single(
        f"kube_pod_container_resource_requests{{container='build', pod='{pod}'}}",
        time=time,
    )
    job.cpu_request = extract_value(
        next(
            (rr for rr in resource_requests if rr["metric"]["resource"] == "cpu"),
            None,
        )
    )
    job.memory_request = extract_value(
        next(
            (rr for rr in resource_requests if rr["metric"]["resource"] == "memory"),
            None,
        )
    )

    # list where one entry is cpu, the other is mem
    resource_limits = client.query_single(
        f"kube_pod_container_resource_limits{{container='build', pod='{pod}'}}",
        time=time,
    )
    job.cpu_limit = extract_value(
        next(
            (rr for rr in resource_limits if rr["metric"]["resource"] == "cpu"),
            None,
        )
    )
    job.memory_limit = extract_value(
        next(
            (rr for rr in resource_limits if rr["metric"]["resource"] == "memory"),
            None,
        )
    )


def annotate_job_annotations_and_labels(
    job: Job, client: PrometheusClient, time: datetime
):
    """Annotate the job model with any necessary fields, returning the pod it ran on."""
    annotations = client.query_single(
        f"kube_pod_annotations{{annotation_gitlab_ci_job_id='{job.job_id}'}}",
        time=time,
    )[0]["metric"]

    # Get pod labels
    pod = annotations["pod"]
    labels = client.query_single(f"kube_pod_labels{{pod='{pod}'}}", time=time)
    labels = labels[0]["metric"]

    job.package_name = annotations["annotation_metrics_spack_job_spec_pkg_name"]
    job.package_version = annotations["annotation_metrics_spack_job_spec_pkg_version"]
    job.compiler_name = annotations["annotation_metrics_spack_job_spec_compiler_name"]
    job.compiler_version = annotations[
        "annotation_metrics_spack_job_spec_compiler_version"
    ]
    job.arch = annotations["annotation_metrics_spack_job_spec_arch"]
    job.package_variants = annotations["annotation_metrics_spack_job_spec_variants"]
    job.build_jobs = annotations["annotation_metrics_spack_job_build_jobs"]
    job.job_size = labels["label_gitlab_ci_job_size"]
    job.stack = labels["label_metrics_spack_ci_stack_name"]

    return pod


def annotate_job_node_data(
    job: Job,
    pod: str,
    client: PrometheusClient,
    time: datetime,
):
    # Use this query to get the node the pod was running on at the time
    pod_info_query = f"kube_pod_info{{pod='{pod}'}}"
    pod_info = client.query_single(pod_info_query, time=time)
    if len(pod_info) > 1:
        raise Exception(
            f"Multiple values receieved for prometheus query {pod_info_query}"
        )
    job.node_name = pod_info[0]["metric"]["node"]

    # Get the node system_uuid from the node name
    node_info = client.query_single(
        f"kube_node_info{{node='{job.node_name}'}}", time=time
    )
    job.node_system_uuid = node_info[0]["metric"]["system_uuid"]

    # Get node labels
    node_labels = client.query_single(
        f"kube_node_labels{{node='{job.node_name}'}}", time=time
    )
    job.node_cpu = int(node_labels[0]["metric"]["label_karpenter_k8s_aws_instance_cpu"])

    # It seems these values are in Megabytes (base 1000)
    mem = node_labels[0]["metric"]["label_karpenter_k8s_aws_instance_memory"]
    job.node_memory = int(parse_quantity(f"{mem}M"))
    job.node_capacity_type = node_labels[0]["metric"][
        "label_karpenter_sh_capacity_type"
    ]
    job.node_instance_type = node_labels[0]["metric"][
        "label_node_kubernetes_io_instance_type"
    ]

    # Retrieve the price of this node
    zone = node_labels[0]["metric"]["label_topology_kubernetes_io_zone"]
    job.node_instance_type_spot_price = client.query_single(
        "karpenter_cloudprovider_instance_type_price_estimate{"
        f"capacity_type='{job.node_capacity_type}',"
        f"instance_type='{job.node_instance_type}',"
        f"zone='{zone}'"
        "}",
        time=time,
    )[0]["value"][1]


def annotate_job_with_prometheus_data(job: Job, client: PrometheusClient):
    # Params for prometheus query
    time = job.started_at + (job.duration / 2)

    # Get pod name and base (unsaved) job
    pod = annotate_job_annotations_and_labels(job, client=client, time=time)
    annotate_job_node_data(job=job, pod=pod, client=client, time=time)
    annotate_job_resource_requests_and_limits(
        job=job, pod=pod, client=client, time=time
    )
