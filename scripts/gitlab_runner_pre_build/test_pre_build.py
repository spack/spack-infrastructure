import pytest
from pytest_lazyfixture import lazy_fixture

from .pre_build import _gitlab_token_to_credentials


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
    urlopen = mocker.patch("urllib.request.urlopen")
    urlencode = mocker.patch("urllib.parse.urlencode")

    mocker.patch(
        "os.environ",
        {
            "PR_BINARY_MIRROR_ROLE_ARN": "arn:aws:iam::123456789012:role/PRBinaryMirrorRole",
            "PROTECTED_BINARY_MIRROR_ROLE_ARN": "arn:aws:iam::123456789012:role/ProtectedBinaryMirrorRole",
            "PR_BINARY_MIRROR_BUCKET_ARN": "arn:aws:s3:::pr-binary-mirror",
            "CI_JOB_ID": "11274",
            "CI_COMMIT_SHORT_SHA": "486b4e605",
            "CI_COMMIT_REF_NAME": "refs/heads/feature",
        },
    )

    _gitlab_token_to_credentials(jwt)

    assert urlencode.call_count == 1
    assert urlencode.call_args_list[0].args[0]["RoleArn"] == expected_role_arn

    if access_type == "pr":
        assert urlencode.call_args_list[0].args[0]["Policy"]
