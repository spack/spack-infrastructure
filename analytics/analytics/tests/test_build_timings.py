import json
import pytest
from analytics.job_log_uploader import upload_job_log
from analytics.build_timing_processor import upload_build_timings

from analytics.models import Timer


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
def test_upload_build_timings(build_json_string):
    upload_build_timings(build_json_string)

    assert Timer.objects.exists()


@pytest.mark.django_db
def test_upload_job_logs(build_json_string):
    upload_job_log(build_json_string)
