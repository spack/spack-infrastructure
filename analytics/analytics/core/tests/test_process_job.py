import pathlib

import pytest

from analytics.job_processor import process_job

examples = pathlib.Path(__file__).parent / "example_payloads"


@pytest.mark.django_db
@pytest.mark.parametrize("payload_path", examples.iterdir())
def test_process_job_known_payloads(payload_path: pathlib.Path):
    with open(payload_path) as f:
        data = f.read()
        process_job(data)
