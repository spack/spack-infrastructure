# Runner Node Certificate Controller

## Overview

The Runner Node Certificate Controller is a Kubernetes CronJob that fixes CSR (Certificate Signing Request) timing issues that cause GitLab CI job failures on newly created runner nodes.

## Problem

### The Issue
When Karpenter creates new EKS nodes for GitLab runners, there's a timing gap where:

1. **Node becomes "Ready"** in Kubernetes
1. **Pod scheduling begins** immediately
1. **Node certificates are still being provisioned** by EKS
1. **GitLab runner pods fail** with `error dialing backend: remote error: tls: internal error`
1. **Jobs fail within 1-2 seconds** before certificates are fully ready

This affects many jobs that land on newly created nodes, causing frequent CI failures and requiring manual job retries.

### Root Cause
The EKS node certificate provisioning process completes after the node is marked as "Ready", creating a race condition where workloads can be scheduled before the node can successfully communicate with the Kubernetes API server.

See this issue for more details https://github.com/awslabs/amazon-eks-ami/issues/1944.

## Solution

### How It Works
1. **Karpenter creates nodes** with a `node.spack.io/certificate-pending=true:NoSchedule` taint
1. **Workloads are blocked** from scheduling on the tainted node
1. **Certificate Controller runs every minute** checking for tainted runner nodes
1. **Controller waits** for nodes to be Ready
1. **Taint is removed** once certificates are confirmed working
1. **Workloads can now safely schedule** on the node

### Karpenter Configuration
Nodes must be created with the certificate-pending taint. This requires the Karpenter EC2NodeClass
for each GitLab runner to apply the `node.spack.io/certificate-pending` taint as a `startupTaint`.
