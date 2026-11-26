import base64
import json
import time
import urllib.parse, urllib.error
import pytest
from pytest_lazyfixture import lazy_fixture

from .pre_build import (
    _gitlab_token_to_credentials,
    _durable_assume_role_request,
    _token_to_sts_request,
)


class MockResponse:
    def __init__(self, code):
        self.code = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def getcode(self):
        return self.code

    def read(self):
        return b'{"AssumeRoleWithWebIdentityResponse":{"AssumeRoleWithWebIdentityResult":{"Credentials":{}}}}'


@pytest.fixture
def pr_jwt():
    """
    {
        "sub": "project_path:spack/spack:ref_type:branch:ref:pr1234",
        "aud": "pr_binary_mirror",
        "iat": 1516239022,
        "iss": "https://gitlab.spack.io"
    }
    """
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9qZWN0X3BhdGg6c3BhY2svc3BhY2s6cmVmX3R5cGU6YnJhbmNoOnJlZjpwcjEyMzQiLCJhdWQiOiJwcl9iaW5hcnlfbWlycm9yIiwiaWF0IjoxNTE2MjM5MDIyLCJpc3MiOiJodHRwczovL2dpdGxhYi5zcGFjay5pbyJ9.aFCczPa5OOvuH6ka9fjFTffIMvasIoO2viYRK0QYEpOWB00HoATu3bjJSuwlNwYyHFklyCne1n5HeHIytmPuOmqbA6mncQaalUlC94c7uLKRQzCBF7XzzZBwE3Ki6ovhT4geTS_MIJeWqxUAv8yp3RBFPLh0kNxWhdzo39w7ZVKNOSHHWkeAbAqt9dtHw3HycwXeq53Zs2Tv7KkhRjOX47DqYM2cIKpoRK_Du5t7TGQuaXGKqjARQhu71OFlcR4qIPuPIc7UtfDJ7DMCl3bXVR2xDjypQ1sxdh1--vLb90xBvQ9fBSUxv5h5ptdrc0qO2TGoJKGJ5eTnjPI_2S4HGQ"


@pytest.fixture
def protected_jwt():
    """
    {
        "sub": "project_path:spack/spack:ref_type:branch:ref:develop",
        "aud": "protected_binary_mirror",
        "iat": 1516239022,
        "iss": "https://gitlab.spack.io"
    }
    """
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9qZWN0X3BhdGg6c3BhY2svc3BhY2s6cmVmX3R5cGU6YnJhbmNoOnJlZjpkZXZlbG9wIiwiYXVkIjoicHJvdGVjdGVkX2JpbmFyeV9taXJyb3IiLCJpYXQiOjE1MTYyMzkwMjIsImlzcyI6Imh0dHBzOi8vZ2l0bGFiLnNwYWNrLmlvIn0.Vhu-Y43sP30dpopO_zrphbmAfss5Ap_qD3nlGGZ0vOLynbAb1GUeloLd08tQSxgoO4CY89SZwtA8UHyBEIeVMfTlPNt-GIZCYVb1JeiZ2212GWosAYlYicwEKGV4ngkqU7AwFMkm4l4AT7UkZbSOGGTBQ1sF2v9-Bnuq3_Ub0kN3Ak0sEUatXoQoIK9oC3sjgTqfqqY7AnZMxwvq8-QV7wHkdhguO58apFJmBXkY_eQgXbLhj_qe3nzaEyDBFey_G21aufBpvOZiz6ZjkHSAsDmnTIBxO6d2NpnpU-6G9F4LxRIZ5GEXIg5bntEP6nubbzw9MM9jtynX1oHSrVNxPg"


@pytest.fixture
def invalid_audience_jwt():
    """
    {
        "sub": "project_path:spack/spack:ref_type:branch:ref:develop",
        "aud": "unknown_audience",
        "iat": 1516239022,
        "iss": "https://gitlab.spack.io"
    }
    """
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9qZWN0X3BhdGg6c3BhY2svc3BhY2s6cmVmX3R5cGU6YnJhbmNoOnJlZjpkZXZlbG9wIiwiYXVkIjoidW5rbm93bl9hdWRpZW5jZSIsImlhdCI6MTUxNjIzOTAyMiwiaXNzIjoiaHR0cHM6Ly9naXRsYWIuc3BhY2suaW8ifQ.HBlbJhNbEqOmiBWwcelFDElcSy_--ioxttS9HjufL58"


@pytest.mark.parametrize(
    "duration, expected",
    [(None, 43200), ("", 43200), ("3600", 3600), ("900", 900), ("43200", 43200)],
)
def test_credentials_duration(duration, expected, monkeypatch):
    monkeypatch.setenv("PROTECTED_BINARY_MIRROR_ROLE_ARN", "arn:aws:iam::123456789012:role/R")
    monkeypatch.setenv("CI_JOB_ID", "11274")
    monkeypatch.setenv("CI_COMMIT_SHORT_SHA", "486b4e605")
    if duration is None:
        monkeypatch.delenv("SPACK_CI_CREDENTIALS_DURATION", raising=False)
    else:
        monkeypatch.setenv("SPACK_CI_CREDENTIALS_DURATION", duration)

    request = _token_to_sts_request("jwt", {"aud": "protected_binary_mirror"})

    assert request["DurationSeconds"] == expected


@pytest.mark.parametrize("duration", ["899", "43201", "one hour"])
def test_credentials_duration_invalid(duration, monkeypatch):
    monkeypatch.setenv("PROTECTED_BINARY_MIRROR_ROLE_ARN", "arn:aws:iam::123456789012:role/R")
    monkeypatch.setenv("CI_JOB_ID", "11274")
    monkeypatch.setenv("CI_COMMIT_SHORT_SHA", "486b4e605")
    monkeypatch.setenv("SPACK_CI_CREDENTIALS_DURATION", duration)

    with pytest.raises(ValueError):
        _token_to_sts_request("jwt", {"aud": "protected_binary_mirror"})


def _make_jwt(payload):
    # JWTs use unpadded URL-safe base64; the signature isn't checked here
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_gitlab_token_expired():
    jwt = _make_jwt({"aud": "protected_binary_mirror", "exp": int(time.time()) - 60})

    with pytest.raises(ValueError, match="expired"):
        _gitlab_token_to_credentials(jwt)


def test_gitlab_token_urlsafe_payload():
    jwt = _make_jwt({"sub": "project_path:spack/spack:ref_type:branch:ref:pr-1>?", "aud": "x"})
    assert "-" in jwt or "_" in jwt

    # decoding succeeds, so the audience check is what rejects it
    with pytest.raises(ValueError, match="Unknown audience"):
        _gitlab_token_to_credentials(jwt)


def test_gitlab_token_requires_valid_audience(invalid_audience_jwt):
    with pytest.raises(ValueError):
        _gitlab_token_to_credentials(invalid_audience_jwt)


@pytest.mark.parametrize(
    "jwt, access_type, expected_role_arn",
    [
        (
            lazy_fixture("pr_jwt"),
            "pr",
            "arn:aws:iam::123456789012:role/PRBinaryMirrorRole",
        ),
        (
            lazy_fixture("protected_jwt"),
            "protected",
            "arn:aws:iam::123456789012:role/ProtectedBinaryMirrorRole",
        ),
    ],
)
def test_gitlab_token_to_credentials(jwt, access_type, expected_role_arn, mocker):
    mocker.patch("urllib.request.urlopen", return_value=MockResponse(200))
    request = mocker.patch("urllib.request.Request")

    mocker.patch(
        "os.environ",
        {
            "PR_BINARY_MIRROR_ROLE_ARN": "arn:aws:iam::123456789012:role/PRBinaryMirrorRole",
            "PROTECTED_BINARY_MIRROR_ROLE_ARN": "arn:aws:iam::123456789012:role/ProtectedBinaryMirrorRole",
            "PR_BINARY_MIRROR_BUCKET_ARN": "arn:aws:s3:::pr-binary-mirror",
            "CI_JOB_ID": "11274",
            "CI_COMMIT_SHORT_SHA": "486b4e605",
            "CI_PROJECT_NAME": "spack",
            "CI_COMMIT_REF_NAME": "refs/heads/feature",
        },
    )

    _gitlab_token_to_credentials(jwt)

    assert request.call_count == 1
    qs = urllib.parse.parse_qs(request.call_args_list[0].args[0].split("?")[1])
    assert qs["RoleArn"][0] == expected_role_arn
    if access_type == "pr":
        assert "Policy" in qs

@pytest.mark.parametrize(
        ('flaky_exception'),
        [
            urllib.error.HTTPError("someurl", 400, "Internal Server Error", None, None),
            urllib.error.URLError("a timeout"),
        ],
        ids=["HTTPError", "URLError"]
)
def test_assume_role_request_eventually_succeeds(mocker, flaky_exception):
    def flaky_urlopen(*args, **kwargs):
        if not flaky_urlopen.has_failed:
            flaky_urlopen.has_failed = True
            raise flaky_exception
        else:
            return MockResponse(200)

    flaky_urlopen.has_failed = False

    mocker.patch("urllib.request.urlopen", side_effect=flaky_urlopen)
    mocker.patch("urllib.request.Request")
    mocker.patch("time.sleep", side_effect=lambda x: None)

    _durable_assume_role_request({})


def test_assume_role_request_fails(mocker):
    def failing_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(
            "someurl", 400, "Internal Server Error", None, None
        )

    mocker.patch("urllib.request.urlopen", side_effect=failing_urlopen)
    mocker.patch("urllib.request.Request")
    mocker.patch("time.sleep", side_effect=lambda x: None)

    with pytest.raises(Exception, match="Failed to assume role"):
        _durable_assume_role_request({})


def test_assume_role_request_doesnt_retry_true_errors(mocker):
    def failing_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(
            "someurl", 403, "Forbidden", None, None
        )

    mocker.patch("urllib.request.urlopen", side_effect=failing_urlopen)
    mocker.patch("urllib.request.Request")
    sleep = mocker.spy(time, "sleep")

    with pytest.raises(Exception):
        _durable_assume_role_request({})

    assert sleep.call_count == 0
