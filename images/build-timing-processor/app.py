import functools
import json
import re
from pathlib import Path

import sentry_sdk
import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from kubernetes import client, config

sentry_sdk.init(
    # Sample only 1% of requests
    traces_sample_rate=0.01,
)

config.load_incluster_config()
v1 = client.CoreV1Api()
batch = client.BatchV1Api()

app = FastAPI()


BUILD_STAGE_REGEX = r"^stage-\d+$"


@functools.cache
def gitlab_url():
    cluster_name = v1.read_namespaced_config_map(
        name="cluster-info", namespace="kube-system"
    ).data["cluster-name"]

    prefix = ".staging" if cluster_name == "spack-staging" else ""
    return f"https://gitlab{prefix}.spack.io"


@app.post("/")
async def gitlab_webhook_consumer(request: Request):
    """
    This endpoint receives the gitlab webhook for succeeded jobs and creates
    a k8s job to push the job timing data to postgres.
    """
    job_input_data = await request.json()
    if job_input_data.get("object_kind", "") != "build":
        raise HTTPException(status_code=400, detail="Invalid request")

    # Exit if not a build stage
    if not re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"]):
        return Response("Skipping non-build stage...")

    # Only process finished and successful jobs
    status = job_input_data["build_status"]
    if status == "failed":
        return Response("Skipping failed job...")
    if status != "success":
        return Response("Skipping in-progress or cancelled job..")

    # Read in job template and set env vars
    with open(Path(__file__).parent / "job-template.yaml") as f:
        job_template = yaml.safe_load(f)
    for container in job_template["spec"]["template"]["spec"]["containers"]:
        container.setdefault("env", []).extend(
            [
                {"name": "JOB_INPUT_DATA", "value": json.dumps(job_input_data)},
                {"name": "GITLAB_URL", "value": gitlab_url()},
            ]
        )

    # Set k8s job name
    job_build_id = str(job_input_data["build_id"])
    job_pipeline_id = str(job_input_data["pipeline_id"])
    job_template["metadata"][
        "name"
    ] = f"build-timing-processing-job-{job_build_id}-{job_pipeline_id}"

    # Add labels to make finding the job that proccessed the error log easier.
    job_template["metadata"]["labels"] = {
        "spack.io/gitlab-build-id": job_build_id,
        "spack.io/gitlab-pipeline-id": job_pipeline_id,
    }

    batch.create_namespaced_job(
        "custom",
        job_template,
    )

    return Response("Upload job dispatched.", status_code=202)
