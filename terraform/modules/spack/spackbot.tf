resource "aws_elasticache_subnet_group" "pr_binary_graduation_task_queue" {
  name       = "pr-binary-graduation-queue-${var.deployment_name}"
  subnet_ids = concat(module.vpc.public_subnets, module.vpc.private_subnets)
}

resource "aws_elasticache_replication_group" "pr_binary_graduation_task_queue" {
  replication_group_id = "pr-binary-graduation-queue-${var.deployment_name}"
  description          = "Used by python RQ module to store pending tasks for workers"

  engine               = "redis"
  engine_version       = "7.0"
  node_type            = "cache.t3.small"
  port                 = 6379
  parameter_group_name = "default.redis7"

  snapshot_retention_limit = 1
  snapshot_window          = "08:30-09:30"

  subnet_group_name          = aws_elasticache_subnet_group.pr_binary_graduation_task_queue.name
  automatic_failover_enabled = true

  replicas_per_node_group = 1
  num_node_groups         = 1

  security_group_ids = [module.eks.node_security_group_id]
}

# The IAM role granting Spackbot full access to spack-binaries-prs S3 bucket.
resource "aws_iam_role" "full_crud_access_spack_binaries_prs" {
  name        = "FullCRUDAccessToBucketSpackBinariesPRs${local.suffix}"
  description = "Managed by Terraform. Grants Kubernetes pods access to read/write/delete objects from the spack-binaries-prs S3 bucket"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "put_spack_binaries_prs" {
  name        = "PutObjectsInBucketSpackBinariesPRs${local.suffix}"
  description = "Managed by Terraform. Grant permission to PutObject for any object in the spack-binaries-prs bucket"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:PutObject",
        "Resource" : "${module.pr_binary_mirror.bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "put_spack_binaries_prs" {
  role       = aws_iam_role.full_crud_access_spack_binaries_prs.name
  policy_arn = aws_iam_policy.put_spack_binaries_prs.arn
}

resource "aws_iam_policy" "delete_spack_binaries_prs" {
  name = "DeleteObjectsFromBucketSpackBinariesPRs${local.suffix}"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:DeleteObject",
        "Resource" : "${module.pr_binary_mirror.bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_spack_binaries_prs" {
  role       = aws_iam_role.full_crud_access_spack_binaries_prs.name
  policy_arn = aws_iam_policy.delete_spack_binaries_prs.arn
}

resource "kubectl_manifest" "spackbot_service_account" {
  for_each  = toset(["spackbot", "spackbotdev"])
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${each.value}-spack-io
      namespace: spack
      annotations:
        # FullCRUDAccessToBucketSpackBinariesPRs
        eks.amazonaws.com/role-arn: ${aws_iam_role.full_crud_access_spack_binaries_prs.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.put_spack_binaries_prs,
    aws_iam_role_policy_attachment.delete_spack_binaries_prs
  ]
}

locals {
  spackbot_token_expires_at = "2025-04-25"
}

resource "gitlab_personal_access_token" "spackbot" {
  user_id    = data.gitlab_user.spackbot.id
  name       = "spackbot personal access token"
  expires_at = local.spackbot_token_expires_at

  scopes = ["api"]

  lifecycle {
    precondition {
      condition     = timecmp(timestamp(), "${local.spackbot_token_expires_at}T00:00:00Z") == -1
      error_message = "The token has expired. Please update the expires_at date."
    }
  }
}

resource "kubectl_manifest" "spackbot_gitlab_credentials" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: spack-bot-gitlab-credentials
      namespace: spack
    data:
      gitlab_token: ${base64encode("${gitlab_personal_access_token.spackbot.token}")}
  YAML
}
