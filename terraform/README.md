# Spack Infrastructure Terraform Configuration

This directory contains the Terraform configuration for the Spack infrastructure. All changes to the AWS cloud infrastructure should be made via this configuration.

## Architecture Overview

We use Terraform to manage the following aspects of the infrastructure:

- **AWS Cloud Infrastructure**: Core AWS infrastructure, including VPC, subnets, NAT gateways, EKS cluster, RDS databases, S3 buckets, etc.
    - For this we use the AWS provider (https://registry.terraform.io/providers/hashicorp/aws/latest/docs), as well as various commmunity modules from the [terraform-aws-modules](https://github.com/terraform-aws-modules) organization (https://registry.terraform.io/namespaces/terraform-aws-modules).
- **Flux**: GitOps deployment tool for managing the Kubernetes cluster
    - For this we use the flux provider (https://registry.terraform.io/providers/fluxcd/flux/latest/docs).
    - The provider does the following:
        - Creates a Flux installation in the EKS cluster
        - Pushes the requisite Flux manifests to the spack-infrastructure github repository (internally, via the Terraform github provider). This is done via a personal access token (PAT) associated with the `spackbot` github account that is stored in AWS Secrets Manager and dynamically retrieved by Terraform at runtime. See [here for an example commit](https://github.com/spack/spack-infrastructure/commit/dd42896897b7c0c0e3e2bca66ae58433fcf734fa).
- **Kubernetes**: Kubernetes yaml manifests for the EKS cluster
    - For this we use the kubectl provider (https://registry.terraform.io/providers/alekc/kubectl/latest/docs) and the helm provider (https://registry.terraform.io/providers/hashicorp/helm/latest/docs).
    - We try to use Flux/GitOps to manage the Kubernetes cluster (i.e., by committing k8s yaml manifests to `k8s/`) as much as possible, but sometimes it is cleaner to manage some manifests with the Terraform kubectl provider. This is true mainly for manifests that have to reference resources that are managed by Terraform. A concrete examples of this is using [the `kubectl_manifest` resource to deploy a `Secret` resource for RDS credentials](./modules/spack_aws_k8s/gitlab_db.tf), which enables us to reference the RDS credentials using Terraform interpolation instead of hardcoding them in a manifest.
    - One special exception is the Karpenter Helm chart, which is the only Helm chart provisioned in this way (i.e., with the Terraform helm provider). This is done to avoid a chicken-and-egg problem with Karpenter; in order for Flux to run and deploy all the other Helm charts and k8s manifests in the git repo, Karpenter must be deployed first in order to provide nodes for them to run on.
- **GitLab**: GitLab instance running on the EKS cluster
  - For this we use the GitLab provider (https://registry.terraform.io/providers/gitlabhq/gitlab/latest/docs). Note: this is strictly for managing resources at the *GitLab* level (GitLab runners, GitLab runner groups, projects, etc.). As such, all of the code for this is in the [spack_gitlab](../modules/spack_gitlab) module so that it only runs *after* the EKS cluster has been provisioned, and Flux has been bootstrapped and deployed the GitLab helm chart.

## Usage

### Bootstrapping

The first time you run this configuration, you will need to run the [terraform-bootstrap](../terraform-bootstrap) configuration to set up the remote state file for the main configuration. As of this writing, the bootstrapping process has been performed, so in most cases you can skip this step; this is only necessary if you need to re-run the bootstrapping process to create a completely new infrastructure deployment (i.e., a third environment, including a third kubernetes cluster, in addition to the existing production and staging environments).

### Running

After the bootstrapping process has been run, you can run the main configuration as follows:
```
cd production/ # (or staging/, if working with the staging environment)
terraform init
terraform plan
terraform apply
```

## Structure

The Terraform configuration is structured as follows:

```
.
├── modules/
│   ├── iam_service_account/ # helper module for creating k8s service accounts w/ IAM roles
│   ├── spack_aws_k8s/       # main module for deploying the infrastructure
│   └── spack_gitlab/        # module for configuring the GitLab instance running on the cluster provisioned by the spack_aws_k8s module
├── production/              # production environment configuration
├── staging/                 # staging environment configuration
```

Each environment has its own directory, and its own Terraform state file (located in S3 - see the `backend "s3"` block in `production/versions.tf` and `staging/versions.tf` for details).

## A Note about Route53/DNS

We use Route53 for DNS management, but unfortunately the Route53 records for the EKS cluster's ELB are not managed by Terraform. This is because the ELB is created automatically by the ingress-nginx Helm chart, and thus Terraform is completely unaware of the ELB's DNS records. As such, we have to manually update the Route53 records for the ELB after the cluster has been provisioned. To do this, go to the Route53 console, find the hosted zone for `*.spack.io` (or `*.staging.spack.io` for staging), and add the record for the EKS cluster's ELB (found in the EC2 console).

## Missing Resources

We adopted Terraform to manage the infrastructure after the initial deployment. As such, there are a few resources that are not yet managed by Terraform. The only known AWS resources that are not managed are the various pieces of the AWS KMS service used for package signing. It is not uncommon to come across other unknown resources that are missing from the Terraform configuration though, and we would like to address this in the future.
