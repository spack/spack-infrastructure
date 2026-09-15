# Terraform modules

Three modules make up a deployment, and they are applied in this order:

```
spack_aws_k8s  ->  spack_flux  ->  spack_gitlab
```

Both `terraform/staging` and `terraform/production` instantiate all three from
their `main.tf`, differing only in region, sizing, and `flux_path`.
`iam_service_account` is a helper used by the others and is not part of the
sequence.

## The order, and what each step depends on

### 1. `spack_aws_k8s`

Everything in AWS: the VPC, the EKS cluster, RDS and ElastiCache for GitLab and
CDash, the binary mirror buckets, IAM roles, the load balancer controller, and
Karpenter. Nothing else can run until the cluster exists.

It exports only three values -- `nat_public_ips`,
`pr_binary_mirror_bucket_name`, and `protected_binary_mirror_bucket_name` --
which is why the ordering below is mostly invisible to Terraform's own graph.

### 2. `spack_flux`

Bootstraps Flux into the cluster with `flux_bootstrap_git`, pointed at
`k8s/staging/` or `k8s/production/`. From that point on, Flux -- not
Terraform -- is what deploys GitLab, the runners, the Karpenter NodePools, and
the CronJobs under `k8s/*/custom/`.

Requires the cluster from step 1: its `flux` provider authenticates via
`data.aws_eks_cluster.spack`, so the cluster must exist before this module can
even be planned.

### 3. `spack_gitlab`

Configures the GitLab instance that Flux deployed in step 2: projects, group and
project settings, webhooks, application settings, runner IAM roles, and the DNS
record for the SSH endpoint.

Requires GitLab to be *running and reachable*, not merely scheduled -- its
`gitlab` provider talks to `https://gitlab[.staging].spack.io` over the network.
It also applies manifests into the `spack` and `custom` namespaces, which Flux
creates, and `gitlab_ssh_dns.tf` reads the `gitlab-gitlab-shell` Service back
out of the cluster.

## Explicit vs. implicit dependencies

Terraform only knows about the dependencies that pass through module outputs:

- `spack_flux` -> `spack_aws_k8s`, via `nat_public_ips`
- `spack_gitlab` -> `spack_aws_k8s`, via the two bucket names and `nat_public_ips`

**There is no dependency edge from `spack_gitlab` to `spack_flux`**, even though
step 3 cannot work until step 2 has converged. Terraform will happily plan them
in parallel. On an existing deployment this is harmless, because GitLab is
already up. On a new one it is the main thing to be aware of.

## Standing up a new deployment

Because both `spack_flux` and `spack_gitlab` read the cluster through data
sources, a plan of the whole configuration fails before the cluster exists.
Apply in stages:

1. `terraform apply -target=module.spack_aws_k8s`
2. `terraform apply -target=module.spack_flux`
3. Wait for Flux to converge -- GitLab in particular takes a while on a first
   install, and the `gitlab-shell` Service needs a load balancer assigned.
4. `terraform apply`

Two failures are expected on the way through and are not signs of a
misconfiguration:

- On non-prod deployments, `spack_gitlab` fails the first time it creates the
  `spack` and `spack-packages` projects. The projects are created with a README
  so that a default branch exists, GitLab protects that branch automatically,
  and the pull mirror -- which only exists outside prod -- cannot
  force-overwrite a protected branch. Delete the branch protection rule in the
  GitLab UI and re-apply. See the comments in `spack_gitlab/gitlab.tf`.
- Data sources that read cluster state -- `gitlab_ssh_dns.tf` here, the gateway
  ALB lookup in `spack_aws_k8s` -- fail until the thing they are reading has
  actually been created. Re-apply once it has.

## Tearing down

Reverse order: `spack_gitlab`, then `spack_flux`, then `spack_aws_k8s`.
Destroying `spack_aws_k8s` first strands the other two, since their providers
cannot authenticate to a cluster that no longer exists.
