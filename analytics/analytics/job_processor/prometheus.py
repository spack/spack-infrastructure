import math
import statistics
from datetime import datetime
from urllib.parse import urlencode

import requests
from kubernetes.utils.quantity import parse_quantity

from analytics.core.models import Job, JobPod, Node

PROM_MAX_RESOLUTION = 10_000


class JobPrometheusDataNotFound(Exception):
    """
    This is raised to indicate that a job's data can't be found in prometheus,
    and was likely not run in the cluster.
    """

    def __init__(self, job_id: int | str):
        super().__init__(f"Job ID: {job_id}")
        self.job_id = job_id


class UnexpectedPrometheusResult(Exception):
    def __init__(self, message: str, query: str) -> None:
        super().__init__(message)
        self.query = query


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
        # URL should include protocol
        self.api_url = f"{url.rstrip('/')}/api/v1"

    def _query(self, method: str, params: dict, single_result: bool):
        if "query" not in params:
            raise RuntimeError("params must include query argument")

        # make request
        query_url = f"{self.api_url}/{method}?{urlencode(params)}"
        res = requests.get(query_url)
        res.raise_for_status()

        # Ensure single result if necessary
        data = res.json()["data"]["result"]
        if single_result:
            if len(data) != 1:
                raise UnexpectedPrometheusResult(
                    message=f"Expected a single value, received {len(data)}.",
                    query=params["query"],
                )

            return data[0]

        return data

    def query_single(self, query: str, time: datetime, single_result=False):
        params = {
            "query": query,
            "time": time.timestamp(),
        }

        return self._query(
            method="query",
            params=params,
            single_result=single_result,
        )

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: int,
        single_result=False,
    ):
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }

        return self._query(
            method="query_range",
            params=params,
            single_result=single_result,
        )

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

        # Step is seconds between samples. Use a hundredth of the duration as the step, to ensure
        # we get a proper amount of data.
        step = math.ceil(job.duration.total_seconds() / 100)

        # Get cpu seconds usage
        cpu_seconds_query = (
            f"container_cpu_usage_seconds_total{{container='build', node='{node}'}}"
        )
        results = self.query_range(
            cpu_seconds_query,
            start=job.started_at,
            end=job.finished_at,
            step=step,
        )

        # First, get the cpu utlization by the pod we care about
        # To do this, just get the last value from the response, since that'll be the total of the counter
        pod_results = next(
            (res for res in results if res["metric"]["pod"] == pod), None
        )
        if pod_results is None:
            raise UnexpectedPrometheusResult(
                message=f"Pod {pod} not found in cpu usage query",
                query=cpu_seconds_query,
            )

        job.pod.cpu_usage_seconds = float(pod_results["values"][-1][1])

        # Then use the same cpu usage results to determine node occupancy, since it gives us a timline of pods on this node
        job.pod.node_occupancy = calculate_node_occupancy(results, step)

        # Finally, determine the node memory usage
        memory_usage = self.query_range(
            f"container_memory_working_set_bytes{{container='build', pod='{pod}'}}",
            start=job.started_at,
            end=job.finished_at,
            step=step,
            single_result=True,
        )["values"]

        # Results consist of arrays: [timestamp, "value"]
        byte_values = [int(x) for _, x in memory_usage]
        job.pod.max_mem = max(byte_values)
        job.pod.avg_mem = statistics.mean(byte_values)

    def annotate_annotations_and_labels(self, job: Job):
        """Annotate the job model with any necessary fields, returning the pod it ran on."""
        try:
            annotations: dict = self.query_single(
                f"kube_pod_annotations{{annotation_gitlab_ci_job_id='{job.job_id}'}}",
                time=job.midpoint,
                single_result=True,
            )["metric"]
        except UnexpectedPrometheusResult:
            # Raise this exception instead to indicate that this job can't use prometheus
            raise JobPrometheusDataNotFound(job_id=job.job_id)

        # job.pod is one-to-one and so is always created when a Job is created
        pod = annotations["pod"]
        job.pod = JobPod(name=pod)

        # Get pod labels
        labels = self.query_single(
            f"kube_pod_labels{{pod='{pod}'}}", time=job.midpoint, single_result=True
        )["metric"]

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
        job.job_size = labels["label_gitlab_ci_job_size"]
        job.stack = labels["label_metrics_spack_ci_stack_name"]

        # Build jobs isn't always specified
        job.build_jobs = annotations.get("annotation_metrics_spack_job_build_jobs")

        return pod

    def annotate_node_data(self, job: Job):
        pod = job.pod.name

        # Use this for step value to have a pretty good guarauntee that we'll find the data,
        # without grabbing too much
        step = math.ceil(job.duration.total_seconds() / 10)

        # Use this query to get the node the pod was running on at the time
        node_name = self.query_range(
            f"kube_pod_info{{pod='{pod}', node=~'.+', pod_ip=~'.+'}}",
            start=job.started_at,
            end=job.finished_at,
            step=step,
            single_result=True,
        )["metric"]["node"]

        # Get the node system_uuid from the node name
        node_system_uuid = self.query_single(
            f"kube_node_info{{node='{node_name}'}}",
            time=job.midpoint,
            single_result=True,
        )["metric"]["system_uuid"]

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
            f"kube_node_labels{{node='{node_name}'}}",
            time=job.midpoint,
            single_result=True,
        )["metric"]
        node.cpu = int(node_labels["label_karpenter_k8s_aws_instance_cpu"])

        # It seems these values are in Megabytes (base 1000)
        mem = node_labels["label_karpenter_k8s_aws_instance_memory"]
        node.memory = int(parse_quantity(f"{mem}M"))
        node.capacity_type = node_labels["label_karpenter_sh_capacity_type"]
        node.instance_type = node_labels["label_node_kubernetes_io_instance_type"]

        # Retrieve the price of this node
        zone = node_labels["label_topology_kubernetes_io_zone"]
        node.instance_type_spot_price = self.query_single(
            "karpenter_cloudprovider_instance_type_price_estimate{"
            f"capacity_type='{node.capacity_type}',"
            f"instance_type='{node.instance_type}',"
            f"zone='{zone}'"
            "}",
            time=job.midpoint,
            single_result=True,
        )["value"][1]

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
