import json
from pathlib import Path
import pickle

import pytest

from analytics.core.job_log_uploader import store_job_data
from analytics.core.models.dimensions import (
    JobDataDimension,
    PackageDimension,
    PackageSpecDimension,
)
from analytics.core.models.facts import JobFact
from analytics.job_processor import process_job
from analytics.job_processor.build_timings import create_packages_and_specs


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


# @pytest.mark.skip
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

    assert JobFact.objects.count() == 1
    assert JobDataDimension.objects.count() == 1

    job = JobDataDimension.objects.first()
    assert job is not None
    assert job.unnecessary == unnecessary


# @pytest.mark.skip
@pytest.mark.django_db
def test_upload_job_logs(build_json_string):
    store_job_data(build_json_string)


@pytest.mark.django_db
def test_create_packages_and_specs(mocker):
    spec_json_path = Path(__file__).parent / "data" / "spec.json"
    with open(spec_json_path) as f:
        spec_json = json.load(f)

    picked_job_path = Path(__file__).parent / "data" / "job.pkl"
    with open(picked_job_path, "rb") as f:
        gl_job = pickle.load(f)

    mock = mocker.patch("analytics.job_processor.build_timings.get_spec_json")
    mock.return_value = spec_json

    # Ensure only empty package and package specs exist
    assert not PackageDimension.objects.exclude(name="").exists()
    assert not PackageSpecDimension.objects.exclude(hash="").exists()

    create_packages_and_specs(gl_job)

    assert PackageDimension.objects.exclude(name="").count() == len(
        spec_json["spec"]["nodes"]
    )
    assert PackageSpecDimension.objects.exclude(hash="").count() == len(
        spec_json["spec"]["nodes"]
    )
