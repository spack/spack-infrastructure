#!/usr/bin/env python3

import functools
import json

import boto3
from kubernetes import client, config
from kubernetes.client.models.v1_config_map import V1ConfigMap
from kubernetes.client.models.v1_secret import V1Secret

# Instantiate k8s and secrets manager client
config.load_config()
v1_client = client.CoreV1Api()
secrets_client = boto3.client("secretsmanager")


@functools.cache
def get_cluster_name() -> str:
    config_map: V1ConfigMap = v1_client.read_namespaced_config_map(
        name="cluster-info", namespace="kube-system"
    )
    return config_map.data["cluster-name"]


def sync_secret(secret: V1Secret):
    """Sync the secret to AWS Secrets Manager."""
    name = secret.metadata.name
    namespace = secret.metadata.namespace
    secret_type = secret.type
    data = json.dumps(secret.data)

    # Create secret name
    cluster_name = get_cluster_name()
    unique_secret_name = f"backup__{cluster_name}__{namespace}__{name}"

    # Check for existing secret of same name
    resp = secrets_client.list_secrets(
        Filters=[{"Key": "name", "Values": [unique_secret_name]}],
        MaxResults=1,
    )

    # Create list of tags
    secret_tags = [
        {
            "Key": "backup",
            "Value": "true",
        },
        {
            "Key": "cluster",
            "Value": cluster_name,
        },
        {
            "Key": "namespace",
            "Value": namespace,
        },
        {
            "Key": "name",
            "Value": name,
        },
        {
            "Key": "type",
            "Value": secret_type,
        },
    ]

    # Check if secret already exists
    if len(resp["SecretList"]):
        secret = resp["SecretList"][0]
        secret_id = secret["ARN"]

        # Update secret value
        secrets_client.put_secret_value(
            SecretId=secret_id,
            SecretString=data,
        )

        # Ensure tags are updated
        secrets_client.tag_resource(SecretId=secret_id, Tags=secret_tags)
        print(f"Updated existing secret: {unique_secret_name}")
        return

    # Create new secret
    secrets_client.create_secret(
        Name=unique_secret_name, SecretString=data, Tags=secret_tags
    )
    print(f"Secret created: {unique_secret_name}")


# Watch for all secret changes
for secret in v1_client.list_secret_for_all_namespaces().items:
    sync_secret(secret)
