import math
import statistics
from datetime import datetime
from urllib.parse import urlencode

import requests
from kubernetes.utils.quantity import parse_quantity

from analytics.models import Job, JobPod, Node

PROM_MAX_RESOLUTION = 10_000


class JobPrometheusDataNotFound(Exception):
    pass


class UnexpectedPrometheusResult(Exception):
    pass


def calculate_node_occupancy(data: list[dict], step: int):
    """
    Determine what percentage of the node this pod had over its lifetime.

    This is achieved by summing the number of pods present for all of the selected samples,
    multiplied by the step size (to normalize result across step size), and divided by the
    duration, to return a fraction.
    """
    # Key is the timestamp, value is the number of jobs
    timeline = {}

    # Determine the node occupancy by tracking how many pods were active on the node at each timestamp
    for entry in data:
        for val, _ in entry["values"]:
            if val not in timeline:
                timeline[val] = 0

            timeline[val] += 1

    start = min(timeline.keys())
    end = max(timeline.keys())

    # Remove the first data point, as otherwise we'd be counting an extra time step towards the numerator
    timeline.pop(start)

    return (sum([1 / x for x in timeline.values()]) * step) / (end - start)


class PrometheusClient:
    def __init__(self, url: str) -> None:
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

    def query_range(
        self, query: str, start: datetime, end: datetime, step: int | None = None
    ):
        if step is None:
            step = math.ceil(
                (end.timestamp() - start.timestamp()) / PROM_MAX_RESOLUTION
            )

        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }
        query_params = urlencode(params)
        query_url = f"http://{self.api_url}/query_range?{query_params}"
        res = requests.get(query_url)
        res.raise_for_status()

        return res.json()["data"]["result"]

    def annotate_resource_requests_and_limits(self, job: Job):
        """Annotate cpu and memory resource requests and limits."""
        pod = job.pod.name

        def extract_value(result: dict | None) -> int | float | None:
            if result is None:
                return None

            num = float(result["value"][1])
            if num.is_integer():
                num = int(num)

            return num

        # list where one entry is cpu, the other is mem
        resource_requests = self.query_single(
            f"kube_pod_container_resource_requests{{container='build', pod='{pod}'}}",
            time=job.midpoint,
        )
        job.pod.cpu_request = extract_value(
            next(
                (rr for rr in resource_requests if rr["metric"]["resource"] == "cpu"),
                None,
            )
        )
        job.pod.memory_request = extract_value(
            next(
                (
                    rr
                    for rr in resource_requests
                    if rr["metric"]["resource"] == "memory"
                ),
                None,
            )
        )

        # list where one entry is cpu, the other is mem
        resource_limits = self.query_single(
            f"kube_pod_container_resource_limits{{container='build', pod='{pod}'}}",
            time=job.midpoint,
        )
        job.pod.cpu_limit = extract_value(
            next(
                (rr for rr in resource_limits if rr["metric"]["resource"] == "cpu"),
                None,
            )
        )
        job.pod.memory_limit = extract_value(
            next(
                (rr for rr in resource_limits if rr["metric"]["resource"] == "memory"),
                None,
            )
        )

    def annotate_usage_and_occupancy(self, job: Job):
        node = job.node.name
        pod = job.pod.name

        # Step is seconds between samples
        step = 30

        # Get cpu seconds usage
        results = self.query_range(
            f"container_cpu_usage_seconds_total{{container='build', node='{node}'}}",
            start=job.started_at,
            end=job.finished_at,
            step=step,
        )

        # First, get the cpu utlization by the pod we care about
        # To do this, just get the last value from the response, since that'll be the total of the counter
        pod_results = next(
            (res for res in results if res["metric"]["pod"] == pod), None
        )
        if pod is None:
            raise UnexpectedPrometheusResult(f"Pod {pod} not found in cpu usage query")

        job.pod.cpu_usage_seconds = float(pod_results["values"][-1][1])

        # Then use the same cpu usage results to determine node occupancy, since it gives us a timline of pods on this node
        job.pod.node_occupancy = calculate_node_occupancy(results, step)

        # Finally, determine the node memory usage
        results = self.query_range(
            f"container_memory_working_set_bytes{{container='build', pod='{pod}'}}",
            start=job.started_at,
            end=job.finished_at,
            step=30,
        )
        if len(results) != 1:
            raise UnexpectedPrometheusResult(
                "Multiple results returned from pod memory query"
            )

        # Results consist of arrays: [timestamp, "value"]
        byte_values = [int(x) for _, x in results[0]["values"]]
        job.pod.max_mem = max(byte_values)
        job.pod.avg_mem = statistics.mean(byte_values)

    def annotate_annotations_and_labels(self, job: Job):
        """Annotate the job model with any necessary fields, returning the pod it ran on."""
        annotations_result = self.query_single(
            f"kube_pod_annotations{{annotation_gitlab_ci_job_id='{job.job_id}'}}",
            time=job.midpoint,
        )
        if len(annotations_result) == 0:
            raise JobPrometheusDataNotFound

        # This field is one-to-one and so is always created when a Job is created
        job.pod = JobPod()

        annotations = annotations_result[0]["metric"]
        job.pod.name = annotations["pod"]
        pod = job.pod.name

        # Get pod labels
        labels = self.query_single(f"kube_pod_labels{{pod='{pod}'}}", time=job.midpoint)
        labels = labels[0]["metric"]

        job.package_name = annotations["annotation_metrics_spack_job_spec_pkg_name"]
        job.package_version = annotations[
            "annotation_metrics_spack_job_spec_pkg_version"
        ]
        job.compiler_name = annotations[
            "annotation_metrics_spack_job_spec_compiler_name"
        ]
        job.compiler_version = annotations[
            "annotation_metrics_spack_job_spec_compiler_version"
        ]
        job.arch = annotations["annotation_metrics_spack_job_spec_arch"]
        job.package_variants = annotations["annotation_metrics_spack_job_spec_variants"]
        job.build_jobs = annotations["annotation_metrics_spack_job_build_jobs"]
        job.job_size = labels["label_gitlab_ci_job_size"]
        job.stack = labels["label_metrics_spack_ci_stack_name"]

        return pod

    def annotate_node_data(self, job: Job):
        pod = job.pod.name

        # Use this query to get the node the pod was running on at the time
        pod_info_query = f"kube_pod_info{{pod='{pod}'}}"
        pod_info = self.query_single(pod_info_query, time=job.midpoint)
        if len(pod_info) > 1:
            raise Exception(
                f"Multiple values receieved for prometheus query {pod_info_query}"
            )
        node_name = pod_info[0]["metric"]["node"]

        # Get the node system_uuid from the node name
        node_info = self.query_single(
            f"kube_node_info{{node='{job.node_name}'}}", time=job.midpoint
        )
        node_system_uuid = node_info[0]["metric"]["system_uuid"]

        # Check if this node has already been created
        existing_node = Node.objects.filter(
            name=node_name, system_uuid=node_system_uuid
        ).first()
        if existing_node is not None:
            job.node = existing_node
            return

        # Create new node
        node = Node(name=node_name, system_uuid=node_system_uuid)

        # Get node labels
        node_labels = self.query_single(
            f"kube_node_labels{{node='{job.node_name}'}}", time=job.midpoint
        )
        node.cpu = int(node_labels[0]["metric"]["label_karpenter_k8s_aws_instance_cpu"])

        # It seems these values are in Megabytes (base 1000)
        mem = node_labels[0]["metric"]["label_karpenter_k8s_aws_instance_memory"]
        node.memory = int(parse_quantity(f"{mem}M"))
        node.capacity_type = node_labels[0]["metric"][
            "label_karpenter_sh_capacity_type"
        ]
        node.instance_type = node_labels[0]["metric"][
            "label_node_kubernetes_io_instance_type"
        ]

        # Retrieve the price of this node
        zone = node_labels[0]["metric"]["label_topology_kubernetes_io_zone"]
        node.instance_type_spot_price = self.query_single(
            "karpenter_cloudprovider_instance_type_price_estimate{"
            f"capacity_type='{job.node_capacity_type}',"
            f"instance_type='{job.node_instance_type}',"
            f"zone='{zone}'"
            "}",
            time=job.midpoint,
        )[0]["value"][1]

        # Save and set as job node
        job.node = node

    def annotate_job(self, job: Job):
        # The order of these functions is important, as they set values on `job` in a specific order

        # After this call, job.pod will be set
        self.annotate_annotations_and_labels(job=job)
        self.annotate_resource_requests_and_limits(job=job)

        # After this call, job.node will be set
        self.annotate_node_data(job=job)

        # This call sets fields on job.pod, but needs job.pod and job.node to be set first
        self.annotate_usage_and_occupancy(job=job)
