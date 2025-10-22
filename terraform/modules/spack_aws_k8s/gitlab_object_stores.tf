resource "aws_s3_bucket" "gitlab_object_stores" {
  for_each = toset(["artifacts", "uploads", "backups", "tmp-storage"])

  bucket = "spack-${var.deployment_name}-gitlab-${each.value}"

  lifecycle {
    prevent_destroy = true
  }
}

# Bucket policy that prevents deletion of GitLab buckets.
resource "aws_s3_bucket_policy" "gitlab_object_stores" {
  for_each = aws_s3_bucket.gitlab_object_stores

  bucket = each.value.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Principal" : "*"
        "Effect" : "Deny",
        "Action" : [
          "s3:DeleteBucket",
        ],
        "Resource" : each.value.arn,
      }
    ]
  })
}

# Lifecycle rule that deletes artifacts older than 3 months
resource "aws_s3_bucket_lifecycle_configuration" "delete_old_artifacts" {
  bucket = aws_s3_bucket.gitlab_object_stores["artifacts"].id

  transition_default_minimum_object_size = "varies_by_storage_class"

  rule {
    id = "DeleteObjectsOlderThan3Months"

    filter {} # Empty filter; all objects in bucket should be affected

    expiration {
      days = 90
    }

    status = "Enabled"
  }
}

resource "aws_iam_policy" "gitlab_object_stores" {
  name        = "GitlabS3Role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. Grants required permissions for GitLab to read/write to relevant S3 buckets."

  # https://docs.gitlab.com/ee/install/aws/manual_install_aws.html#create-an-iam-policy
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:PutObjectAcl",
        ],
        "Resource" : concat(
          [for bucket in aws_s3_bucket.gitlab_object_stores : "${bucket.arn}/*"],
          ["${aws_s3_bucket.gitlab_gitaly_bundle_uri.arn}/*"],
        )
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:ListBucket",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
          "s3:ListBucketMultipartUploads"
        ],
        "Resource" : concat(
          [for bucket in aws_s3_bucket.gitlab_object_stores : bucket.arn],
          [aws_s3_bucket.gitlab_gitaly_bundle_uri.arn],
        )
      }
    ]
  })
}

resource "aws_iam_role" "gitlab_object_stores" {
  name        = "GitlabS3Role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. Role for GitLab to assume so that it can access relevant S3 buckets."
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn,
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

resource "aws_iam_role_policy_attachment" "gitlab_object_stores" {
  role       = aws_iam_role.gitlab_object_stores.name
  policy_arn = aws_iam_policy.gitlab_object_stores.arn
}

locals {
  connection_secret_name = "gitlab-s3-bucket-secrets"
  connection_secret_key  = "connection"

  backups_secret_name = "gitlab-s3-backup-bucket-secrets"
  backups_secret_key  = "config"
}

resource "kubectl_manifest" "gitlab_object_stores_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-s3-bucket-config
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    data:
      values.yaml: |
        global:
          serviceAccount:
            create: true
            enabled: true
            annotations:
              eks.amazonaws.com/role-arn: ${aws_iam_role.gitlab_object_stores.arn}
          # https://docs.gitlab.com/charts/advanced/external-object-storage/#lfs-artifacts-uploads-packages-external-diffs-terraform-state-dependency-proxy-secure-files
          appConfig:
            artifacts:
              bucket: ${aws_s3_bucket.gitlab_object_stores["artifacts"].id}
              connection:
                secret: ${local.connection_secret_name}
                key: ${local.connection_secret_key}
            uploads:
              bucket: ${aws_s3_bucket.gitlab_object_stores["uploads"].id}
              connection:
                secret: ${local.connection_secret_name}
                key: ${local.connection_secret_key}
            backups:
              objectStorage:
                backend: s3
              bucket: ${aws_s3_bucket.gitlab_object_stores["backups"].id}
              tmpBucket: ${aws_s3_bucket.gitlab_object_stores["tmp-storage"].id}
        # https://docs.gitlab.com/charts/advanced/external-object-storage/#backups
        gitlab:
          toolbox:
            backups:
              objectStorage:
                config:
                  secret: ${local.backups_secret_name}
                  key: ${local.backups_secret_key}
          gitaly:
            bundleUri:
              goCloudUrl: "s3://${aws_s3_bucket.gitlab_gitaly_bundle_uri.bucket}?region=${data.aws_region.current.name}"
  YAML
}

resource "kubectl_manifest" "gitlab_object_stores_secret" {
  # https://docs.gitlab.com/charts/charts/globals.html#connection
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.connection_secret_name}
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    stringData:
      ${local.connection_secret_key}: |
        provider: "AWS"
        use_iam_profile: "true"
        region: "${data.aws_region.current.name}"
  YAML
}

resource "kubectl_manifest" "gitlab_object_stores_backup_secret" {
  # https://docs.gitlab.com/charts/advanced/external-object-storage/#backups-storage-example
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.backups_secret_name}
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    stringData:
      ${local.backups_secret_key}: |
        [default]
        bucket_location = ${data.aws_region.current.name}
  YAML
}

# S3 infrastructure for Gitaly Bundle URIs
resource "aws_s3_bucket" "gitlab_gitaly_bundle_uri" {
  bucket = "spack-${var.deployment_name}-gitaly-bundle-storage"
}
