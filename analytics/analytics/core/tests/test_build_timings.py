import json

import pytest

from analytics.core.job_log_uploader import store_job_data
from analytics.core.models.legacy import LegacyJob
from analytics.job_processor import process_job


@pytest.fixture()
def unnecessary_job_json_string():
    return json.dumps(
        {
            "project_id": 2,
            "build_id": 9935713,
            "build_status": "success",
            "project": {"web_url": "https://aspackgitlaburl.test"},
            "ref": "develop",
        }
    )


@pytest.fixture()
def build_json_string():
    return json.dumps(
        {
            "project_id": 2,
            "build_id": 9708962,
            "build_status": "success",
            "project": {"web_url": "https://aspackgitlaburl.test"},
            "ref": "develop",
        }
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "job_json_string,unnecessary",
    [
        ["build_json_string", False],
        ["unnecessary_job_json_string", True],
    ],
)
def test_process_job_unnecessary_jobs(request, job_json_string, unnecessary):
    job_json_string = request.getfixturevalue(job_json_string)
    process_job(job_json_string)

    assert LegacyJob.objects.count() == 1
    assert LegacyJob.objects.first().unnecessary == unnecessary


@pytest.mark.django_db
def test_upload_job_logs(build_json_string):
    store_job_data(build_json_string)
