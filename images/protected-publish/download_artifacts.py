import argparse
import os
import subprocess
import sys

import gitlab


GITLAB_PRIVATE_TOKEN = os.environ.get("GITLAB_TOKEN", None)


def download_generate_artifacts(tag, working_dir):
    if not GITLAB_PRIVATE_TOKEN:
        print("Error: environment variable GITLAB_TOKEN must contain a valid PAT")
        sys.exit(1)

    gl = gitlab.Gitlab(url="https://gitlab.spack.io", private_token=GITLAB_PRIVATE_TOKEN)

    project = gl.projects.get(2)
    pipelines = project.pipelines.list(ref=tag)

    pipeline = pipelines[0]
    jobs = pipeline.jobs.list(get_all=True)

    current_directory = os.getcwd()
    lock_paths = []

    for pipeline_job in jobs:
        if pipeline_job.name.endswith("generate"):
            job = project.jobs.get(pipeline_job.id, lazy=True)
            stack_dir = os.path.join(working_dir, pipeline_job.name)
            artifacts_path = os.path.join(stack_dir, "artifacts.zip")
            os.makedirs(stack_dir, exist_ok=True)
            with open(artifacts_path, "wb") as f:
                job.artifacts(streamed=True, action=f.write)
            os.chdir(stack_dir)
            subprocess.run(["unzip", "-bo", artifacts_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.unlink(artifacts_path)
            os.chdir(current_directory)
            for (dirpath, _, filenames) in os.walk(stack_dir):
                for f in filenames:
                    if f == "spack.lock":
                        lock_paths.append(os.path.join(dirpath,f))

    return lock_paths


def main(tag, working_dir):
    spack_lock_paths = download_generate_artifacts(tag, working_dir)

    for lock_path in spack_lock_paths:
        print(lock_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="download_artifacs",
        description="""Given a ref, download the artifacts of all pipeline
            generation jobs, and print the absolute paths to each one""")

    parser.add_argument("ref", type=str, default="develop", help="Ref (tag or branch) for which you want pipeline artifacts")
    parser.add_argument("--working-dir", type=str, default=os.getcwd(), help="Directory to store artifacts, default is current working dir")
    args = parser.parse_args()

    main(args.ref, args.working_dir)
