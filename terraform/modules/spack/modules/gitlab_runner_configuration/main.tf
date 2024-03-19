terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "16.3.0"
    }
  }
}

locals {
  gitlab_domain = "gitlab${var.deployment_name == "prod" ? "" : ".staging"}.spack.io"

  mirror_roles = {
    "pr_binary_mirror" = {
      "role_name_suffix"     = "PRBinaryMirror${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}",
      "role_arn_ci_var_name" = "PR_BINARY_MIRROR_ROLE_ARN",
      "conditions"           = ["project_path:${data.gitlab_project.spack.path_with_namespace}:ref_type:branch:ref:pr*"],
    },
    "protected_binary_mirror" = {
      "role_name_suffix"     = "ProtectedBinaryMirror${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}",
      "role_arn_ci_var_name" = "PROTECTED_BINARY_MIRROR_ROLE_ARN",
      "conditions" = [
        "project_path:${data.gitlab_project.spack.path_with_namespace}:ref_type:branch:ref:develop",
        "project_path:${data.gitlab_project.spack.path_with_namespace}:ref_type:branch:ref:releases/v*",
        "project_path:${data.gitlab_project.spack.path_with_namespace}:ref_type:tag:ref:develop-*",
        "project_path:${data.gitlab_project.spack.path_with_namespace}:ref_type:tag:ref:v*"
      ],
    }
  }
}

data "aws_caller_identity" "current" {}

data "gitlab_project" "spack" {
  path_with_namespace = "spack/spack"
}


data "tls_certificate" "gitlab" {
  url = "https://${local.gitlab_domain}"
}

resource "aws_iam_openid_connect_provider" "gitlab" {
  url             = "https://${local.gitlab_domain}"
  client_id_list  = keys(local.mirror_roles)
  thumbprint_list = [data.tls_certificate.gitlab.certificates.0.sha1_fingerprint]
}

data "aws_iam_policy_document" "gitlab_oidc_assume_role" {
  for_each = local.mirror_roles

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.gitlab_domain}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.gitlab_domain}:aud"
      values   = [each.key]
    }

    condition {
      test     = "StringLike"
      variable = "${local.gitlab_domain}:sub"
      values   = each.value.conditions
    }
  }
}

resource "aws_iam_role" "gitlab_runner" {
  for_each = data.aws_iam_policy_document.gitlab_oidc_assume_role

  name                 = "GitLabRunner${local.mirror_roles[each.key].role_name_suffix}"
  assume_role_policy   = each.value.json
  max_session_duration = 3600 * 6 # only allow a max of 6 hours for a session to be active
}

data "aws_iam_policy_document" "gitlab_runner" {
  for_each = var.deployment_name == "staging" ? local.mirror_roles : {}

  statement {
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:DeleteObject"]

    resources = [
      each.key == "protected_binary_mirror" ? "${var.protected_binary_bucket_arn}/*" : "${var.pr_binary_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_policy" "gitlab_runner" {
  for_each = data.aws_iam_policy_document.gitlab_runner

  name        = "WriteBinariesTo${local.mirror_roles[each.key].role_name_suffix}"
  description = "Managed by Terraform. IAM Policy that provides access to S3 buckets for binary mirrors."
  policy      = each.value.json
}

resource "aws_iam_role_policy_attachment" "gitlab_runner" {
  for_each = aws_iam_policy.gitlab_runner

  role       = aws_iam_role.gitlab_runner[each.key].name
  policy_arn = each.value.arn
}

resource "gitlab_project_variable" "binary_mirror_role_arn" {
  for_each = resource.aws_iam_role.gitlab_runner

  project = data.gitlab_project.spack.id
  key     = local.mirror_roles[each.key].role_arn_ci_var_name
  value   = each.value.arn
}

# pre_build.py needs access to this to request PR prefix scoped permissions
resource "gitlab_project_variable" "pr_binary_mirror_bucket_arn" {
  project = data.gitlab_project.spack.id
  key     = "PR_BINARY_MIRROR_BUCKET_ARN"
  value   = var.pr_binary_bucket_arn
}

# attachments for the pre-existing hardcoded policies in production
resource "aws_iam_role_policy_attachment" "legacy_gitlab_runner_pr_binary_mirror" {
  for_each = var.deployment_name == "prod" ? toset(["arn:aws:iam::588562868276:policy/DeleteObjectsFromBucketSpackBinariesPRs",
  "arn:aws:iam::588562868276:policy/PutObjectsInBucketSpackBinariesPRs"]) : []

  role       = aws_iam_role.gitlab_runner["pr_binary_mirror"].name
  policy_arn = each.value
}

resource "aws_iam_role_policy_attachment" "legacy_gitlab_runner_protected_binary_mirror" {
  for_each = var.deployment_name == "prod" ? toset(["arn:aws:iam::588562868276:policy/DeleteObjectsFromBucketSpackBinaries",
  "arn:aws:iam::588562868276:policy/PutObjectsInBucketSpackBinaries"]) : []

  role       = aws_iam_role.gitlab_runner["protected_binary_mirror"].name
  policy_arn = each.value
}
