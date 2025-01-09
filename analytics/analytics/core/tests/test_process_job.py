import json
import pathlib

import faker
import pytest
from gitlab.v4.objects import Project, ProjectJob

from analytics.job_processor import process_job
from analytics.job_processor.utils import RetryInfo, get_gitlab_handle

examples = pathlib.Path(__file__).parent / "data" / "example_payloads"



@pytest.fixture(autouse=True, scope='session')
def mock_gitlab_db():
    from django.conf import settings
    del settings.DATABASES['gitlab']
    yield



# mock prometheus response
# multiple
# {
#     "status": "success",
#     "data": {
#         "resultType": "matrix",
#         "result": []
#     }
# }
# single
# {
#     "status": "success",
#     "data": {
#         "resultType": "vector",
#         "result": []
#     }
# }

@pytest.mark.django_db(databases=['default'])
@pytest.mark.parametrize("payload_path", examples.iterdir())
def test_process_job_known_payloads(payload_path: pathlib.Path, mocker, mock_gitlab_db):
    def mock_trace(*args, **kwargs):
        return faker.Faker().text(max_nb_chars=4000).encode()

    mock_job_trace = mocker.patch.object(ProjectJob, "trace", new=mock_trace)

    with open(payload_path) as f:
        payload_str = f.read()
        payload = json.loads(payload_str)

    gl = get_gitlab_handle()
    mock_project = Project(
        manager=gl.projects,
        attrs={
            "id": payload["project_id"],
            "description": "",
            "name": "spack",
            "namespace": {
                "id": 4,
                "name": "spack",
                "path": "spack",
                "kind": "group",
                "full_path": "spack",
                "parent_id": None,
                "avatar_url": None,
            },
        },
    )

    def fix_timestr(t: str):
        return t.replace(" UTC", "Z").replace(" ", "T")

    mock_job = ProjectJob(
        manager=gl.projects,
        attrs={
            "id": payload["build_id"],
            "name": payload["build_name"],
            "stage": payload["build_stage"],
            "status": payload["build_status"],
            "created_at": fix_timestr(payload["build_created_at"]),
            "started_at": fix_timestr(payload["build_started_at"]),
            "finished_at": fix_timestr(payload["build_finished_at"]),
            "duration": payload["build_duration"],
            "runner": payload["runner"],
        },
    )

    mock_get_job_retry_data = mocker.patch("analytics.job_processor.dimensions.get_job_retry_data", new=RetryInfo(is_retry=False, is_manual_retry=False, attempt_number=1, final_attempt=False))

    mock_get_gitlab_project = mocker.patch(
        "analytics.job_processor.get_gitlab_project", new=lambda x: mock_project
    )
    # mock_get_gitlab_project.return_value = mock_project

    mock_get_gitlab_job = mocker.patch(
        "analytics.job_processor.get_gitlab_job", new=lambda project, job_id: mock_job
    )
    # mock_get_gitlab_job.return_value = mock_job

    # breakpoint()

    process_job(payload_str)
