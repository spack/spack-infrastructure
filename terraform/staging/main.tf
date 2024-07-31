terraform {
  required_version = "~> 1.5.2"

  backend "s3" {
    bucket         = "spack-terraform-state-staging"
    key            = "terraform.tfstate"
    region         = "us-west-1"
    dynamodb_table = "spack-terraform-state-locks-staging"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.5"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0.0"
    }
    flux = {
      source  = "fluxcd/flux"
      version = "1.3.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 5.13.0"
    }
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "16.3.0"
    }
  }
}

variable "eks_cluster_role" {
  type        = string
  description = "Role for Terraform to assume that grants access to the EKS cluster."
  default     = null
}

locals {
  eks_cluster_role = coalesce(var.eks_cluster_role, module.staging_cluster.cluster_access_role_arn)
}

provider "aws" {
  region = "us-west-2"
}

provider "helm" {
  kubernetes {
    host                   = module.staging_cluster.cluster_endpoint
    cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--region", "us-west-2",
        "--cluster-name", module.staging_cluster.cluster_name,
        "--role", local.eks_cluster_role,
      ]
    }
  }
}

provider "kubectl" {
  host                   = module.staging_cluster.cluster_endpoint
  cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--region", "us-west-2",
      "--cluster-name", module.staging_cluster.cluster_name,
      "--role", local.eks_cluster_role,
    ]
  }
}

provider "kubernetes" {
  host                   = module.staging_cluster.cluster_endpoint
  cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--region", "us-west-2",
      "--cluster-name", module.staging_cluster.cluster_name,
      "--role", local.eks_cluster_role,
    ]
  }
}


provider "github" {
  owner = "spack"
  token = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
}

data "kubernetes_ingress_v1" "gitlab_webservice" {
  metadata {
    name      = "gitlab-webservice-default"
    namespace = "gitlab"
  }
}

locals {
  gitlab_url = "https://${data.kubernetes_ingress_v1.gitlab_webservice.spec[0].rule[0].host}"
}

provider "gitlab" {
  base_url = local.gitlab_url
  token    = jsondecode(data.aws_secretsmanager_secret_version.gitlab_token.secret_string).gitlab_terraform_provider_access_token
}

module "staging_cluster" {
  source = "../modules/spack"

  deployment_name = "staging"

  gitlab_url = local.gitlab_url

  kubernetes_version = "1.29"

  availability_zones = ["us-west-2a", "us-west-2b", "us-west-2c", "us-west-2d"]

  vpc_cidr = "192.168.0.0/16"
  public_subnets = [
    "192.168.0.0/19",
    "192.168.32.0/19",
    "192.168.64.0/19",
    "192.168.96.0/19",
  ]
  private_subnets = [
    "192.168.128.0/19",
    "192.168.160.0/19",
    "192.168.192.0/19",
    "192.168.224.0/19",
  ]

  # Use cheap DB instances for staging deployment
  cdash_db_instance_class = "db.t3.small"

  gitlab_db_instance_class            = "db.t3.small"
  gitlab_db_master_credentials_secret = "arn:aws:secretsmanager:us-west-2:588562868276:secret:gitlab-staging-master-credentials-q5Fynz"

  analytics_db_credentials_secret = "arn:aws:secretsmanager:us-west-2:588562868276:secret:analytics-staging-master-password-jZI8NA"

  elasticache_instance_class = "cache.t4g.small"

  # Use a cheap OpenSearch instance for staging deployment
  opensearch_instance_type = "t3.small.search"
  opensearch_volume_size   = 100

  ses_email_domain = "staging.spack.io"

  github_actions_oidc_arn = data.aws_iam_openid_connect_provider.github_actions.arn
}
