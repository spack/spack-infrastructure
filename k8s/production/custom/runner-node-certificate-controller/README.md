# Runner Node Certificate Controller

## Overview

The Runner Node Certificate Controller is a Kubernetes CronJob that fixes CSR (Certificate Signing Request) timing issues that cause GitLab CI job failures on newly created runner nodes.

## Problem

### The Issue
When Karpenter creates new EKS nodes for GitLab runners, there's a timing gap where:

1. **Node becomes "Ready"** in Kubernetes
2. **Pod scheduling begins** immediately
3. **Node certificates are still being provisioned** by EKS
4. **GitLab runner pods fail** with `error dialing backend: remote error: tls: internal error`
5. **Jobs fail within 1-2 seconds** before certificates are fully ready

This affects many jobs that land on newly created nodes, causing frequent CI failures and requiring manual job retries.

### Root Cause
The EKS node certificate provisioning process completes after the node is marked as "Ready", creating a race condition where workloads can be scheduled before the node can successfully communicate with the Kubernetes API server.

## Solution

### How It Works
1. **Karpenter creates nodes** with a `node.spack.io/certificate-pending=true:NoSchedule` taint
2. **Workloads are blocked** from scheduling on the tainted node
3. **Certificate Controller runs every minute** checking for tainted runner nodes
4. **Controller waits** for nodes to be Ready + 2 minutes for certificate stabilization
5. **Taint is removed** once certificates are confirmed working
6. **Workloads can now safely schedule** on the node

### Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Karpenter     │───▶│   New EKS Node   │───▶│  Certificate Ready  │
│                 │    │                  │    │                     │
│ Creates node    │    │ Status: Ready    │    │ Taint: Removed      │
│ with taint      │    │ Taint: Applied   │    │ Jobs: Can schedule  │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                              │                          ▲
                              ▼                          │
                       ┌──────────────────┐             │
                       │  Cert Controller │─────────────┘
                       │                  │
                       │ Runs every 1min  │
                       │ Removes taint    │
                       │ when ready       │
                       └──────────────────┘
```

### Karpenter Configuration
Nodes must be created with the certificate-pending taint. This requires the Karpenter EC2NodeClass
for each GitLab runner to apply the `node.spack.io/certificate-pending` taint as a `startupTaint`.
