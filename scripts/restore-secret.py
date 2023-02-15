#!/usr/bin/env python3

import json
import re

import boto3
import click
from kubernetes import client, config
from kubernetes.client.models.v1_secret_list import V1SecretList

# Load k8s config
config.load_kube_config()

# Setup aws client
secrets_client = boto3.client("secretsmanager")


def get_secret_tag(key: str, tags: list[dict[str, str]]):
    for d in tags:
        if d["Key"] == key:
            return d["Value"]

    raise Exception("Tag not found")


def get_context_cluster_name(context: dict):
    arn = context["context"]["cluster"]
    match = re.match(r"arn:aws:eks:[a-z0-9-]+:588562868276:cluster\/(.+)", arn)
    return match.group(1)


def get_v1_client(cluster_name: str):
    # Get cluster context that matches the provided cluster name
    contexts = config.list_kube_config_contexts()[0]
    matching = [c for c in contexts if get_context_cluster_name(c) == cluster_name]
    if len(matching) > 1:
        raise click.ClickException(
            f"Multiple contexts found for cluster {cluster_name}."
        )
    if not matching:
        raise click.ClickException(f"No contexts found for cluster {cluster_name}")

    # Return client with context
    return client.CoreV1Api(
        api_client=config.new_client_from_config(context=matching[0]["name"])
    )


@click.command(help="Restore a secret from AWS Secrets Manager to the cluster")
@click.argument("secret-arn")
@click.option(
    "-f", "--force", is_flag=True, help="Overwrite existing secrets if found."
)
def cmd(secret_arn, force):
    # Retrieve cluster name, secret namespace and name
    tags = secrets_client.describe_secret(SecretId=secret_arn)["Tags"]
    cluster_name = get_secret_tag("cluster", tags)
    secret_namespace = get_secret_tag("namespace", tags)
    secret_name = get_secret_tag("name", tags)
    secret_type = get_secret_tag("type", tags)

    # Get k8s client
    k8s_client = get_v1_client(cluster_name)

    # Check if secret exists
    exists = False
    try:
        k8s_client.read_namespaced_secret(name=secret_name, namespace=secret_namespace)
        exists = True
        if not force:
            raise click.ClickException(
                f"Secret {secret_name} already exists in namespace {secret_namespace}."
                " Please run with the -f flag to overwrite."
            )
    except client.ApiException:
        # Secret doesn't currently exist, do nothing.
        pass

    # Get backed up secret value
    secret_data = json.loads(
        secrets_client.get_secret_value(SecretId=secret_arn)["SecretString"]
    )

    # Create secret body
    new_secret_body = client.V1Secret(
        api_version="v1",
        kind="Secret",
        type=secret_type,
        metadata={"name": secret_name},
        data=secret_data,
    )

    # Create secret if it doesn't exist, else patch
    if not exists:
        k8s_client.create_namespaced_secret(
            namespace=secret_namespace, body=new_secret_body
        )
        print(f"Secret {secret_name} in namespace {secret_namespace} created!")
    else:
        k8s_client.patch_namespaced_secret(
            namespace=secret_namespace, name=secret_name, body=new_secret_body
        )
        print(f"Secret {secret_name} in namespace {secret_namespace} updated!")


if __name__ == "__main__":
    cmd()
