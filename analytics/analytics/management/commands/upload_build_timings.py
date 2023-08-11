import json
import os
import re
import tempfile
import zipfile

import djclick as click
import gitlab
from gitlab.v4.objects import Project, ProjectJob

from analytics.models import Job, Phase, Timer

# Other constants
PACKAGE_NAME_REGEX = r"(.+)/[a-zA-Z0-9]+ .+"

# Instantiate gitlab api wrapper
GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.spack.io")
gl = gitlab.Gitlab(GITLAB_URL, GITLAB_TOKEN)

# Grab job data
JOB_INPUT_DATA = os.environ["JOB_INPUT_DATA"]


def create_job(project: Project, job: ProjectJob) -> Job:
    # Grab package name and runner tags
    package_name = re.match(PACKAGE_NAME_REGEX, job.name).group(1)
    runner_tags = gl.runners.get(job.runner["id"]).tag_list

    # Return created job
    return Job.objects.create(
        job_id=job.get_id(),
        project_id=project.get_id(),
        name=job.name,
        started_at=job.started_at,
        duration=job.duration,
        ref=job.ref,
        tags=job.tag_list,
        package_name=package_name,
        aws=("aws" in runner_tags),
    )


def get_timings_json(job: ProjectJob) -> dict | None:
    # Download job artifacts and parse timings json
    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
        artifacts_file = temp.name
        with open(artifacts_file, "wb") as f:
            job.artifacts(streamed=True, action=f.write)

        # Read in timing json
        try:
            timing_filename = "jobs_scratch_dir/user_data/install_times.json"
            with zipfile.ZipFile(artifacts_file) as zfile:
                with zfile.open(timing_filename) as timing_file:
                    return json.load(timing_file)
        except KeyError:
            pass

    return None


@click.command()
def main():
    # Read input data and extract params
    job_input_data = json.loads(JOB_INPUT_DATA)
    job_id = job_input_data["build_id"]

    # Retrieve project and job from gitlab API
    gl_project = gl.projects.get(job_input_data["project_id"])
    gl_job = gl_project.jobs.get(job_input_data["build_id"])

    # Get or create job record
    job = Job.objects.filter(job_id=job_id).first()
    if job is None:
        job = create_job(gl_project, gl_job)

    # Get timings
    timings: list[dict] | None = get_timings_json(gl_job)
    if not timings:
        return

    # Iterate through each timer and create timers and phase results
    phases = []
    for entry in timings:
        # Sometimes name can be missing, skip if so
        if "name" not in entry:
            continue

        # Create timer
        timer = Timer.objects.create(
            name=entry.get("name"),
            hash=entry.get("hash"),
            cache=entry["cache"],
            time_total=entry["total"],
            job=job,
        )

        # Add all phases to bulk phase list
        phases.extend(
            [
                Phase(
                    timer=timer,
                    name=phase["name"],
                    path=phase["path"],
                    seconds=phase["seconds"],
                    count=phase["count"],
                )
                for phase in entry["phases"]
            ]
        )

    # Bulk create phases
    Phase.objects.bulk_create(phases)


if __name__ == "__main__":
    main()
