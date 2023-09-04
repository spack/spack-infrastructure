"""
This script is responsible for taking the GITLAB_OIDC_TOKEN from the environment and
exchanging it for temporary AWS credentials. These credentials are then printed to stdout to be
sourced by the gitlab runner in its pre_build configuration option.

In the case of a PR build, the temporary credentials are scoped down to only allow access to the
S3 bucket prefix for the relevant PR.
"""
import boto3, os, sys, jwt, json

TEMPORARY_CREDENTIALS_DURATION = 3600 * 6  # 6 hours

if __name__ == "__main__":
    if not os.environ.get("GITLAB_OIDC_TOKEN"):
        print("GITLAB_OIDC_TOKEN not in the environment", file=sys.stderr)
        sys.exit(0)  # this isn't an error yet.

    token = jwt.decode(
        os.environ["GITLAB_OIDC_TOKEN"],
        algorithms=["RS256"],
        # it's unnecessary to verify the signature here since this is running before any
        # untrusted code. it's also useful to avoid having to install the crypto libraries
        # in diverse environments.
        options={"verify_signature": False},
    )

    # assemble aws sts temporary credential request
    sts = boto3.client("sts")

    assume_role_kwargs = {
        "RoleArn": os.environ[
            "PR_BINARY_MIRROR_ROLE_ARN"
            if token["aud"] == "pr_binary_mirror"
            else "PROTECTED_BINARY_MIRROR_ROLE_ARN"
        ],
        "RoleSessionName": (
            f'GitLabRunner-{os.environ["CI_JOB_ID"]}-{os.environ["CI_COMMIT_SHORT_SHA"]}'
        ),
        "WebIdentityToken": os.environ["GITLAB_OIDC_TOKEN"],
        "DurationSeconds": TEMPORARY_CREDENTIALS_DURATION,
    }

    # if this is a PR build, narrow down the permissions to only allow access to the PR build prefix
    if token["aud"] == "pr_binary_mirror":
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

    print(
        f"Assuming role {assume_role_kwargs['RoleArn']} with session name {assume_role_kwargs['RoleSessionName']}",
        file=sys.stderr,
    )
    response = sts.assume_role_with_web_identity(**assume_role_kwargs)

    # print credentials to stdout
    print(f'export AWS_ACCESS_KEY_ID="{response["Credentials"]["AccessKeyId"]}"')
    print(
        f'export AWS_SECRET_ACCESS_KEY="{response["Credentials"]["SecretAccessKey"]}"'
    )
    print(f'export AWS_SESSION_TOKEN="{response["Credentials"]["SessionToken"]}"')
