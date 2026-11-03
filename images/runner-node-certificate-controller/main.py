#!/usr/bin/env -S uv run
"""
Runner Node Certificate Controller

This script manages certificate-pending taints on runner nodes in a Kubernetes cluster.
It verifies that node certificates are working properly before removing the taint.
"""

from datetime import datetime, timezone

import sentry_sdk
from kubernetes import client, config

TAINT_KEY = "node.spack.io/certificate-pending"

sentry_sdk.init(traces_sample_rate=0.1)


def get_k8s_clients() -> tuple[client.CoreV1Api, client.CertificatesV1Api]:
    """Load kubernetes config and return API clients"""
    config.load_incluster_config()

    return client.CoreV1Api(), client.CertificatesV1Api()


def remove_taint_from_node(v1_client: client.CoreV1Api, node_name: str) -> bool:
    """Remove certificate-pending taint from a node"""
    print(f"Removing certificate-pending taint from node: {node_name}")

    # Get current node
    node = v1_client.read_node(name=node_name)

    # Remove the taint
    if node.spec and node.spec.taints:
        filtered_taints = [t for t in node.spec.taints if t.key != TAINT_KEY]
        if not filtered_taints:
            return False
        node.spec.taints = filtered_taints if filtered_taints else None

    # Update the node
    v1_client.patch_node(name=node_name, body=node)
    print(f"✓ Successfully removed taint from {node_name}")
    return True


def is_node_ready(v1_client: client.CoreV1Api, node_name: str) -> bool:
    """Check if node is ready"""
    node = v1_client.read_node_status(name=node_name)
    if node.status and node.status.conditions:
        for condition in node.status.conditions:
            if condition.type == "Ready":
                return condition.status == "True"
    return False


def verify_node_certificates(
    v1_client: client.CoreV1Api, cert_client: client.CertificatesV1Api, node_name: str
) -> bool:
    """Verify node certificates are actually working"""
    print(f"  🔍 Verifying certificates are functional on {node_name}...")

    csr_list = cert_client.list_certificate_signing_request()
    approved_csrs = []

    for csr in csr_list.items:
        if csr.spec.username and node_name in csr.spec.username:
            if csr.status and csr.status.conditions:
                if any(c.type == "Approved" for c in csr.status.conditions):
                    approved_csrs.append(csr.metadata.name)

    if not approved_csrs:
        print(f"  ❌ No approved CSRs found for node {node_name}")
        return False

    print(f"  ✅ Found approved CSRs for node: {', '.join(approved_csrs)}")

    # Kubelet connectivity is covered by the Ready check in main(). We don't
    # probe kubelet endpoints directly because that requires nodes/proxy,
    # which would let this service account exec into pods on any node.

    node = v1_client.read_node_status(name=node_name)
    if node.status and node.status.conditions:
        for condition in node.status.conditions:
            reason = condition.reason or ""
            message = condition.message or ""

            if reason == "KubeletNotReady" or "certificate" in message.lower():
                print(f"  ❌ Certificate-related issues found: {message}")
                return False

    print("  ✅ No certificate-related issues in node conditions")
    print(f"  🎉 All certificate checks passed for {node_name}")
    return True


def get_node_age_seconds(v1_client: client.CoreV1Api, node_name: str) -> int:
    """Get node age in seconds"""
    node = v1_client.read_node(name=node_name)
    if node.metadata and node.metadata.creation_timestamp:
        current_dt = datetime.now(timezone.utc)
        age_seconds = int(
            (current_dt - node.metadata.creation_timestamp).total_seconds()
        )
        return age_seconds
    return 0


def get_tainted_runner_nodes(v1_client: client.CoreV1Api) -> list[str]:
    """Find all runner nodes with certificate-pending taint"""
    print("Finding runner nodes with certificate-pending taint...")

    nodes = v1_client.list_node(label_selector="spack.io/pipeline=true")
    tainted_nodes = []

    for node in nodes.items:
        node_name = node.metadata.name
        if node.spec.taints:
            # Check if this node has our taint
            if any(taint.key == TAINT_KEY for taint in node.spec.taints):
                tainted_nodes.append(node_name)

    return tainted_nodes


def main():
    print(f"=== Runner Node Certificate Controller - {datetime.now()} ===")

    # Get Kubernetes clients
    v1_client, cert_client = get_k8s_clients()

    # Find tainted nodes
    tainted_nodes = get_tainted_runner_nodes(v1_client)

    if not tainted_nodes:
        print("No runner nodes found with certificate-pending taint")
        print("=== Job Complete ===")
        return

    print("Found nodes with certificate-pending taint:")
    for node in tainted_nodes:
        print(node)
    print()

    # Process each tainted node
    processed = 0
    removed = 0

    for node in tainted_nodes:
        print(f"Processing node: {node}")
        processed += 1

        # Log node age for reference
        node_age = get_node_age_seconds(v1_client, node)
        print(f"  Node age: {node_age}s")

        # Check if node is ready
        if not is_node_ready(v1_client, node):
            print("  ⏳ Node not Ready yet, keeping taint")
            continue

        print("  ✓ Node is Ready, now verifying certificates...")

        # Verify certificates are actually working
        if verify_node_certificates(v1_client, cert_client, node):
            print("  ✅ Certificates verified, removing taint")
            if remove_taint_from_node(v1_client, node):
                removed += 1
        else:
            print("  ❌ Certificate verification failed, keeping taint for now")
            print("  ℹ️  Will retry on next run")
        print()

    print("=== Summary ===")
    print(f"Processed nodes: {processed}")
    print(f"Removed taints: {removed}")
    print("=== Job Complete ===")


if __name__ == "__main__":
    main()
