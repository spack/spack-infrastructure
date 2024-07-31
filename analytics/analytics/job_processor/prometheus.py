import math
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from dateutil.parser import isoparse
from gitlab.v4.objects import ProjectJob
from kubernetes.utils.quantity import parse_quantity

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


@dataclass
class PodCpuRequestsLimits:
    cpu_request: float | None
    cpu_limit: float | None
    memory_request: float | None
    memory_limit: float | None


@dataclass
class PodResourceUsage:
    cpu_usage_seconds: float
    node_occupancy: float
    max_memory: int
    avg_memory: float


@dataclass
class PodLabels:
    package_hash: str
    package_name: str
    package_version: str
    compiler_name: str
    compiler_version: str
    arch: str
    package_variants: str
    job_size: str
    stack: str
    build_jobs: int | None


@dataclass
class NodeData:
    name: str
    system_uuid: uuid.UUID
    cpu: int
    memory: int
    capacity_type: str
    instance_type: str
    spot_price: float


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
    @staticmethod
    def _default_range_step(duration: float):
        return math.ceil(duration / 10)

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
        step: int | None = None,
        single_result=False,
    ):
        step = step or self._default_range_step((end - start).total_seconds())
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

    def get_pod_resource_requests_and_limits(
        self, pod: str, start: datetime, end: datetime
    ) -> PodCpuRequestsLimits:
        """Get cpu and memory resource requests and limits."""

        def extract_first_value(result: dict | None) -> int | float | None:
            if result is None:
                return None

            num = float(result["values"][0][1])
            if num.is_integer():
                num = int(num)

            return num

        # Result is a list where one entry is cpu, the other is mem
        resource_requests = self.query_range(
            f"kube_pod_container_resource_requests{{container='build', pod='{pod}'}}",
            start=start,
            end=end,
        )

        cpu_request = extract_first_value(
            next(
                (rr for rr in resource_requests if rr["metric"]["resource"] == "cpu"),
                None,
            )
        )
        memory_request = extract_first_value(
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
        resource_limits = self.query_range(
            f"kube_pod_container_resource_limits{{container='build', pod='{pod}'}}",
            start=start,
            end=end,
        )
        cpu_limit = extract_first_value(
            next(
                (rr for rr in resource_limits if rr["metric"]["resource"] == "cpu"),
                None,
            )
        )
        memory_limit = extract_first_value(
            next(
                (rr for rr in resource_limits if rr["metric"]["resource"] == "memory"),
                None,
            )
        )

        return PodCpuRequestsLimits(
            cpu_request=cpu_request,
            cpu_limit=cpu_limit,
            memory_request=memory_request,
            memory_limit=memory_limit,
        )

    def get_pod_usage_and_occupancy(
        self, pod: str, node: str, start: datetime, end: datetime
    ) -> PodResourceUsage:
        duration = end - start

        # Custom step for finer grain results
        step = math.ceil(duration.total_seconds() / 100)

        # Get cpu seconds usage
        cpu_seconds_query = (
            f"container_cpu_usage_seconds_total{{container='build', node='{node}'}}"
        )
        results = self.query_range(
            cpu_seconds_query,
            start=start,
            end=end,
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

        cpu_usage_seconds = float(pod_results["values"][-1][1])

        # Then use the same cpu usage results to determine node occupancy, since it gives us a timline of pods on this node
        node_occupancy = calculate_node_occupancy(results, step)

        # Finally, determine the node memory usage
        memory_usage = self.query_range(
            f"container_memory_working_set_bytes{{container='build', pod='{pod}'}}",
            start=start,
            end=end,
            step=step,
            single_result=True,
        )["values"]

        # Results consist of arrays: [timestamp, "value"]
        byte_values = [int(x) for _, x in memory_usage]
        max_mem = max(byte_values)
        avg_mem = statistics.mean(byte_values)

        return PodResourceUsage(
            cpu_usage_seconds=cpu_usage_seconds,
            node_occupancy=node_occupancy,
            max_memory=max_mem,
            avg_memory=avg_mem,
        )

    def get_pod_name_from_gitlab_job(self, gljob: ProjectJob) -> str | None:
        started_at = isoparse(gljob.started_at)
        duration = timedelta(seconds=gljob.duration)
        finished_at = isoparse(gljob.started_at) + duration

        step = math.ceil(duration.total_seconds() / 10)
        try:
            annotations: dict = self.query_range(
                f"kube_pod_annotations{{annotation_gitlab_ci_job_id='{gljob.get_id()}'}}",
                start=started_at,
                end=finished_at,
                step=step,
                single_result=True,
            )["metric"]
        except UnexpectedPrometheusResult:
            return None

        return annotations["pod"]

    def get_pod_labels(self, pod: str, start: datetime, end: datetime) -> PodLabels:
        """Get pod annotations and labels."""
        # Get pod annotations
        annotations: dict = self.query_range(
            f"kube_pod_annotations{{pod='{pod}'}}",
            start=start,
            end=end,
            single_result=True,
        )["metric"]

        # Get pod labels
        labels = self.query_range(
            f"kube_pod_labels{{pod='{pod}'}}", start=start, end=end, single_result=True
        )["metric"]

        package_hash = annotations["annotation_metrics_spack_job_spec_hash"]
        package_name = annotations["annotation_metrics_spack_job_spec_pkg_name"]
        package_version = annotations["annotation_metrics_spack_job_spec_pkg_version"]
        compiler_name = annotations["annotation_metrics_spack_job_spec_compiler_name"]
        compiler_version = annotations[
            "annotation_metrics_spack_job_spec_compiler_version"
        ]
        arch = annotations["annotation_metrics_spack_job_spec_arch"]
        package_variants = annotations["annotation_metrics_spack_job_spec_variants"]
        job_size = labels["label_gitlab_ci_job_size"]
        stack = labels["label_metrics_spack_ci_stack_name"]

        # Build jobs isn't always specified
        build_jobs = annotations.get("annotation_metrics_spack_job_build_jobs")
        if build_jobs is not None:
            build_jobs = int(build_jobs)

        return PodLabels(
            package_hash=package_hash,
            package_name=package_name,
            package_version=package_version,
            compiler_name=compiler_name,
            compiler_version=compiler_version,
            arch=arch,
            package_variants=package_variants,
            job_size=job_size,
            stack=stack,
            build_jobs=build_jobs,
        )

    def get_pod_node_data(self, pod: str, start: datetime, end: datetime) -> NodeData:
        # Use this query to get the node the pod was running on at the time
        node_name = self.query_range(
            f"kube_pod_info{{pod='{pod}', node=~'.+', pod_ip=~'.+'}}",
            start=start,
            end=end,
            single_result=True,
        )["metric"]["node"]

        # Get the node system_uuid from the node name
        node_system_uuid = uuid.UUID(
            self.query_range(
                f"kube_node_info{{node='{node_name}'}}",
                start=start,
                end=end,
                single_result=True,
            )["metric"]["system_uuid"]
        )

        # Get node labels. Include extra labels to prevent the results being split up
        # into two sets (one before this label was added and one after). This can occur if
        # the job is scheduled on a newly created node
        node_labels = self.query_range(
            f"kube_node_labels{{node='{node_name}', label_karpenter_sh_initialized='true', label_topology_ebs_csi_aws_com_zone=~'.+'}}",
            start=start,
            end=end,
            single_result=True,
        )["metric"]
        cpu = int(node_labels["label_karpenter_k8s_aws_instance_cpu"])

        # It seems these values are in Megabytes (base 1000)
        memory = int(
            parse_quantity(f"{node_labels['label_karpenter_k8s_aws_instance_memory']}M")
        )
        capacity_type = node_labels["label_karpenter_sh_capacity_type"]
        instance_type = node_labels["label_node_kubernetes_io_instance_type"]

        # Retrieve the price of this node. Since this price can change in the middle of this job's
        # lifetime, we return all values from this query and average them.
        zone = node_labels["label_topology_kubernetes_io_zone"]
        spot_prices_result = self.query_range(
            f"""
            karpenter_cloudprovider_instance_type_price_estimate{{
                capacity_type='{capacity_type}',
                instance_type='{instance_type}',
                zone='{zone}'
            }}""",
            start=start,
            end=end,
        )
        spot_price = statistics.mean(
            [float(val[1]) for result in spot_prices_result for val in result["values"]]
        )

        # Save and set as job node
        return NodeData(
            name=node_name,
            system_uuid=node_system_uuid,
            cpu=cpu,
            memory=memory,
            capacity_type=capacity_type,
            instance_type=instance_type,
            spot_price=spot_price,
        )
