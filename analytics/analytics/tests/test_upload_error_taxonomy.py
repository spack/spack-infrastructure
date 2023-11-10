import json
import random
import threading
from datetime import datetime
from typing import Any

import pytest

from analytics.models import ErrorTaxonomy, Job

JOB_TRACES = {
    8826259: """
        ERROR: No files to upload
        Cleaning up project directory and file based variables
        00:00
        ERROR: Error cleaning up pod: pods "runner-eu8s7xzf-project-2-concurrent-0-mu17vi7t" not found
        ERROR: Job failed (system failure): error sending request: Post "https://10.100.0.1:443/api/v1/namespaces/pipeline/pods/runner-eu8s7xzf-project-2-concurrent-0-mu17vi7t/attach?container=build&stdin=true": EOF
    """,
    8825911: """
        To reproduce this build locally, run:
            spack ci reproduce-build https://gitlab.spack.io/api/v4/projects/2/jobs/8825911/artifacts [--working-dir <dir>] [--autostart]
        If this project does not have public pipelines, you will need to first:
            export GITLAB_PRIVATE_TOKEN=<generated_token>
        ... then follow the printed instructions.
        Running after_script
        00:01
        Running after script...
        $ cat /proc/loadavg || true
        1.08 4.31 8.79 1/748 1261
        Uploading artifacts for failed job
        00:01
        Uploading artifacts...
        jobs_scratch_dir/logs: found 1 matching artifact files and directories
        jobs_scratch_dir/reproduction: found 8 matching artifact files and directories
        jobs_scratch_dir/tests: found 2 matching artifact files and directories
        jobs_scratch_dir/user_data: found 3 matching artifact files and directories
        Uploading artifacts as "archive" to coordinator... 201 Created  id=8825911 responseStatus=201 Created token=64_Cxyrv
        Cleaning up project directory and file based variables
        00:01
        ERROR: Job failed: command terminated with exit code 1
    """,
    9043674: """
        RuntimeError: concretization failed for the following reasons:
            1. acts: '%gcc@:7' conflicts with '@0.23:'
            2. acts: '%gcc@:7' conflicts with '@0.23:'
                    required because conflict applies to spec @0.23:
                    required because acts+analysis+binaries+dd4hep+edm4hep+examples+fatras+geant4+hepmc3+identification+podio+pythia8+python+tgeo requested from CLI
                    required because conflict is triggered when %gcc@:7
                    required because acts+analysis+binaries+dd4hep+edm4hep+examples+fatras+geant4+hepmc3+identification+podio+pythia8+python+tgeo requested from CLI
            Running after_script
            00:00
            Running after script...
            $ cat /proc/loadavg || true
            13.58 10.67 7.56 1/1785 12
            Cleaning up project directory and file based variables
            00:00
            ERROR: Job failed: exit code 1
    """,
}


@pytest.fixture()
def mock_gitlab(monkeypatch: pytest.MonkeyPatch):
    # Mock env vars
    IGNORED_ENV_VARS = (
        "GITLAB_TOKEN",
        "GITLAB_POSTGRES_DB",
        "GITLAB_POSTGRES_RO_USER",
        "GITLAB_POSTGRES_RO_PASSWORD",
        "GITLAB_POSTGRES_HOST",
    )
    for env_var in IGNORED_ENV_VARS:
        monkeypatch.setenv(env_var, "foobar")

    # Now that env vars are properly mocked, we can import this module
    from analytics.management.commands import upload_error_taxonomy

    # Mock calls to gitlab API and database
    monkeypatch.setattr(
        upload_error_taxonomy,
        "get_job_trace",
        lambda project_id, job_id: JOB_TRACES[job_id],
    )
    monkeypatch.setattr(
        upload_error_taxonomy, "job_retry_data", lambda *args, **kwargs: (1, 0)
    )


@pytest.mark.parametrize(
    ["job_webhook_payload", "expected_taxonomy"],
    [
        (
            {
                "object_kind": "build",
                "ref": "develop",
                "tag": False,
                "before_sha": "a6466b9dddf59cc185800ac428bd4ba535b96c2e",
                "sha": "a452e8379e12bd46925df30b99cf4b30edf80457",
                "retries_count": 1,
                "build_id": 8825911,
                "build_name": "visit@3.3.3 /jbgulft %gcc@11.1.0 arch=linux-ubuntu20.04-x86_64_v3 Data and Vis SDK",
                "build_stage": "stage-20",
                "build_status": "failed",
                "build_created_at": "2023-10-23 15:09:56 UTC",
                "build_started_at": "2023-10-23 17:55:04 UTC",
                "build_finished_at": "2023-10-23 17:58:32 UTC",
                "build_duration": 208.425831,
                "build_queued_duration": 10.771205,
                "build_allow_failure": False,
                "build_failure_reason": "script_failure",
                "pipeline_id": 529203,
                "runner": {
                    "id": 19462,
                    "description": "runner-x86-v4-prot-gitlab-runner-79b97d7974-2hj5n",
                    "runner_type": "instance_type",
                    "active": True,
                    "is_shared": True,
                    "tags": [
                        "x86_64",
                        "x86_64_v2",
                        "x86_64_v3",
                        "x86_64_v4",
                        "avx",
                        "avx2",
                        "avx512",
                        "small",
                        "medium",
                        "large",
                        "huge",
                        "protected",
                        "aws",
                        "spack",
                    ],
                },
                "project_id": 2,
                "project_name": "spack / spack",
                "user": {
                    "id": 3,
                    "name": "Spack Bot",
                    "username": "spackbot",
                    "avatar_url": "https://gitlab.spack.io/uploads/-/system/user/avatar/3/57643519.png",
                    "email": "[REDACTED]",
                },
                "commit": {
                    "id": 529203,
                    "name": None,
                    "sha": "a452e8379e12bd46925df30b99cf4b30edf80457",
                    "message": "nghttp2: add v1.57.0 (#40652)\n\n",
                    "author_name": "Harmen Stoppels",
                    "author_email": "[REDACTED]",
                    "author_url": "mailto:me@harmenstoppels.nl",
                    "status": "running",
                    "duration": None,
                    "started_at": "2023-10-23 15:10:25 UTC",
                    "finished_at": None,
                },
                "repository": {
                    "name": "spack",
                    "url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "description": "",
                    "homepage": "https://gitlab.spack.io/spack/spack",
                    "git_http_url": "https://gitlab.spack.io/spack/spack.git",
                    "git_ssh_url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "visibility_level": 20,
                },
                "project": {
                    "id": 2,
                    "name": "spack",
                    "description": "",
                    "web_url": "https://gitlab.spack.io/spack/spack",
                    "avatar_url": None,
                    "git_ssh_url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "git_http_url": "https://gitlab.spack.io/spack/spack.git",
                    "namespace": "spack",
                    "visibility_level": 20,
                    "path_with_namespace": "spack/spack",
                    "default_branch": "develop",
                    "ci_config_path": "share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml",
                },
                "environment": None,
                "source_pipeline": {
                    "project": {
                        "id": 2,
                        "web_url": "https://gitlab.spack.io/spack/spack",
                        "path_with_namespace": "spack/spack",
                    },
                    "job_id": 8825079,
                    "pipeline_id": 529171,
                },
            },
            "spack_error",
        ),
        (
            {
                "object_kind": "build",
                "ref": "pr40932_hep-cloud-pipeline",
                "tag": False,
                "before_sha": "0000000000000000000000000000000000000000",
                "sha": "a0d0305f2ff9a9f375010aaa79336d8241b9ab0f",
                "retries_count": 1,
                "build_id": 9043674,
                "build_name": "hep-generate",
                "build_stage": "generate",
                "build_status": "failed",
                "build_created_at": "2023-11-10 14:43:57 UTC",
                "build_started_at": "2023-11-10 14:44:08 UTC",
                "build_finished_at": "2023-11-10 14:47:28 UTC",
                "build_duration": 200.08593,
                "build_queued_duration": 0.261321,
                "build_allow_failure": False,
                "build_failure_reason": "script_failure",
                "pipeline_id": 547935,
                "runner": {
                    "id": 16964,
                    "description": "uo-voltar-cpu-small-medium-1",
                    "runner_type": "instance_type",
                    "active": True,
                    "is_shared": True,
                    "tags": [
                        "avx",
                        "public",
                        "spack",
                        "medium",
                        "avx2",
                        "avx512",
                        "small",
                        "uo",
                        "x86_64",
                        "voltar",
                        "x86_64_v3",
                        "x86_64_v4",
                        "x86_64_v2",
                        "docker",
                        "cpu",
                        "service",
                    ],
                },
                "project_id": 2,
                "project_name": "spack / spack",
                "user": {
                    "id": 3,
                    "name": "Spack Bot",
                    "username": "spackbot",
                    "avatar_url": "https://gitlab.spack.io/uploads/-/system/user/avatar/3/57643519.png",
                    "email": "[REDACTED]",
                },
                "commit": {
                    "id": 547935,
                    "name": None,
                    "sha": "a0d0305f2ff9a9f375010aaa79336d8241b9ab0f",
                    "message": "Merge 78c2eb5afb669bd28c52ae68d13ef49f95432227 into 4027a2139b053251dafc2de38d24eac4d69d42a0\n",
                    "author_name": "spackbot",
                    "author_email": "[REDACTED]",
                    "author_url": "mailto:noreply@spack.io",
                    "status": "running",
                    "duration": None,
                    "started_at": "2023-11-10 14:44:09 UTC",
                    "finished_at": None,
                },
                "repository": {
                    "name": "spack",
                    "url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "description": "",
                    "homepage": "https://gitlab.spack.io/spack/spack",
                    "git_http_url": "https://gitlab.spack.io/spack/spack.git",
                    "git_ssh_url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "visibility_level": 20,
                },
                "project": {
                    "id": 2,
                    "name": "spack",
                    "description": "",
                    "web_url": "https://gitlab.spack.io/spack/spack",
                    "avatar_url": None,
                    "git_ssh_url": "git@ssh.gitlab.spack.io:spack/spack.git",
                    "git_http_url": "https://gitlab.spack.io/spack/spack.git",
                    "namespace": "spack",
                    "visibility_level": 20,
                    "path_with_namespace": "spack/spack",
                    "default_branch": "develop",
                    "ci_config_path": "share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml",
                },
                "environment": None,
            },
            "concretization_error",
        ),
        # TODO: this test case fails.
        # (
        #     {
        #         "before_sha": "a6466b9dddf59cc185800ac428bd4ba535b96c2e",
        #         "build_id": 8826259,
        #         "build_name": "py-scipy@1.5.4 /mscpuhz %gcc@11.3.0 arch=linux-ubuntu22.04-x86_64_v3 Machine Learning",
        #         "build_stage": "stage-13",
        #         "build_status": "failed",
        #         "object_kind": "build",
        #         "ref": "develop",
        #         "retries_count": 1,
        #         "sha": "a452e8379e12bd46925df30b99cf4b30edf80457",
        #         "tag": False,
        #     },
        #     "other",
        # ),
    ],
)
@pytest.mark.django_db()
def test_upload_gitlab_failure_logs(
    job_webhook_payload: dict[str, Any],
    expected_taxonomy: str,
    monkeypatch: pytest.MonkeyPatch,
    mock_gitlab,
):
    from analytics.management.commands import upload_error_taxonomy

    monkeypatch.setenv("JOB_INPUT_DATA", json.dumps(job_webhook_payload))

    def _create_job():
        return Job.objects.create(
            job_id=job_webhook_payload["build_id"],
            project_id=1,
            name="test",
            started_at=datetime.now(),
            duration=200,
            ref="develop",
            tags=["test"],
            package_name="test",
        )

    # Intentionally delay creation of a Job record until after the call to
    # the error taxonomy script. This tests a potential race condition where
    # the error processing job executes before the build timing job.
    threading.Timer(random.randint(5, 10), _create_job).start()

    upload_error_taxonomy.main()

    error_taxonomy_record = ErrorTaxonomy.objects.get(
        job_id=job_webhook_payload["build_id"]
    )

    assert error_taxonomy_record.error_taxonomy == expected_taxonomy
