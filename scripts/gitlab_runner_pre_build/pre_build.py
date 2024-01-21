"""
This script is responsible for taking the GITLAB_OIDC_TOKEN from the environment and
exchanging it for temporary AWS credentials. These credentials are then printed to stdout to be
sourced by the gitlab runner in its pre_build configuration option.

In the case of a PR build, the temporary credentials are scoped down to only allow access to the
S3 bucket prefix for the relevant PR.
"""
import os, sys, json, base64, time
import urllib.request, urllib.parse, urllib.error

TEMPORARY_CREDENTIALS_DURATION = 3600 * 6  # 6 hours


def _token_to_sts_request(raw_jwt, decoded_jwt):
    if decoded_jwt["aud"] not in ["pr_binary_mirror", "protected_binary_mirror"]:
        raise ValueError(f"Unknown audience '{decoded_jwt['aud']}' set on OIDC token.")

    assume_role_kwargs = {
        "RoleArn": os.environ[
            "PR_BINARY_MIRROR_ROLE_ARN"
            if decoded_jwt["aud"] == "pr_binary_mirror"
            else "PROTECTED_BINARY_MIRROR_ROLE_ARN"
        ],
        "RoleSessionName": (
            f'GitLabRunner-{os.environ["CI_JOB_ID"]}-{os.environ["CI_COMMIT_SHORT_SHA"]}'
        ),
        "WebIdentityToken": raw_jwt,
        "DurationSeconds": TEMPORARY_CREDENTIALS_DURATION,
    }

    # if this is a PR build, narrow down the permissions to only allow access to the PR build prefix
    if decoded_jwt["aud"] == "pr_binary_mirror":
        assume_role_kwargs["Policy"] = json.dumps(
            {
                "Statement": [
                    {
                        "Effect": "Allow",
                        # allow every action the broader RoleArn allows
                        "Action": "*",
                        # scope the actions down the pr prefix
                        "Resource": f"{os.environ['PR_BINARY_MIRROR_BUCKET_ARN']}/{os.environ['CI_COMMIT_REF_NAME']}/*",
                    }
                ]
            }
        )

    return assume_role_kwargs


def _durable_assume_role_request(assume_role_kwargs):
    attempts = 0
    max_attempts = 6

    while attempts < max_attempts:
        try:
            req = urllib.request.Request(
                "https://sts.amazonaws.com/?Action=AssumeRoleWithWebIdentity&Version=2011-06-15&"
                + urllib.parse.urlencode(assume_role_kwargs),
                headers={"Accept": "application/json"},
            )

            with urllib.request.urlopen(req) as response:
                if response.getcode() == 200:
                    response = json.loads(response.read().decode("utf-8"))
                    return response
                else:
                    raise ValueError(
                        f"Unexpected response code from assume role request: {response.getcode()}"
                    )
        except urllib.error.HTTPError as e:
            print(e.read().decode("utf-8"), file=sys.stderr)

            if e.code == 400:
                attempts += 1
                print(
                    f"Assume role request failed with 400, retrying ({attempts}/{max_attempts})",
                    file=sys.stderr,
                )
                time.sleep(2 ** (1 + attempts))
            else:
                raise e

    raise Exception(f"Failed to assume role after {max_attempts} attempts")


def _gitlab_token_to_credentials(gitlab_token):
    token = gitlab_token.split(".")[1]
    token += "=" * ((4 - len(token) % 4) % 4)
    token = json.loads(base64.b64decode(token))

    assume_role_kwargs = _token_to_sts_request(gitlab_token, token)

    print(
        f"Assuming role {assume_role_kwargs['RoleArn']} with session name {assume_role_kwargs['RoleSessionName']}... ",
        file=sys.stderr,
        end="",
    )

    response = _durable_assume_role_request(assume_role_kwargs)

    return response["AssumeRoleWithWebIdentityResponse"][
        "AssumeRoleWithWebIdentityResult"
    ]["Credentials"]


if __name__ == "__main__":
    if not os.environ.get("GITLAB_OIDC_TOKEN"):
        print("GITLAB_OIDC_TOKEN not in the environment", file=sys.stderr)
        sys.exit(0)  # this isn't an error yet.

    try:
        response = _gitlab_token_to_credentials(os.environ["GITLAB_OIDC_TOKEN"])

        # print credentials to stdout
        print(f'export AWS_ACCESS_KEY_ID="{response["AccessKeyId"]}"')
        print(f'export AWS_SECRET_ACCESS_KEY="{response["SecretAccessKey"]}"')
        print(f'export AWS_SESSION_TOKEN="{response["SessionToken"]}"')
    except Exception as err:
        if not all(key in os.environ for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]):
            raise err

        print("Falling back to environment credentials.", file=sys.stderr)

    print("done.", file=sys.stderr)
