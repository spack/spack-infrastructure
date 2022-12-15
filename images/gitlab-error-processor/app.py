import json
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from kubernetes import client, config

config.load_incluster_config()

batch = client.BatchV1Api()

app = FastAPI()


@app.post("/")
async def gitlab_webhook_consumer(request: Request):
    """
    This endpoint receives the gitlab webhook for failed jobs and creates
    a k8s job to parse the logs and upload them to opensearch.
    """
    job_input_data = await request.json()

    if job_input_data.get("object_kind", "") != "build":
        raise HTTPException(status_code=400, detail="Invalid request")

    if job_input_data["build_status"] != "failed":
        return Response("Not a failed job, no action needed.", status_code=200)

    with open(Path(__file__).parent / "job-template.yaml") as f:
        job_template = yaml.safe_load(f)

    for container in job_template["spec"]["template"]["spec"]["containers"]:
        container.setdefault("env", []).extend(
            [dict(name="JOB_INPUT_DATA", value=json.dumps(job_input_data))]
        )

    job_build_id = str(job_input_data["build_id"])
    job_pipeline_id = str(job_input_data["pipeline_id"])

    job_template["metadata"][
        "name"
    ] = f"gitlab-error-processing-job-{job_build_id}-{job_pipeline_id}"

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
