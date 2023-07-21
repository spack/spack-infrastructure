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

# Lifecycle rule that deletes artifacts older than 30 days
resource "aws_s3_bucket_lifecycle_configuration" "delete_old_artifacts" {
  bucket = aws_s3_bucket.gitlab_object_stores["artifacts"].id

  rule {
    id = "DeleteObjectsOlderThan30Days"

    filter {} # Empty filter; all objects in bucket should be affected

    expiration {
      days = 30
    }

    status = "Enabled"
  }
}

resource "aws_iam_policy" "gitlab_object_stores" {
  name        = "GitlabS3Role-${var.deployment_name}"
  description = "Managed by Terraform. Grants required permissions for GitLab to read/write to relevant S3 buckets."

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          # https://docs.gitlab.com/ee/install/aws/manual_install_aws.html#create-an-iam-policy
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:PutObjectAcl",
        ],
        "Resource" : [for bucket in aws_s3_bucket.gitlab_object_stores : "${bucket.arn}/*"],
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:ListBucket",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
          "s3:ListBucketMultipartUploads"
        ],
        "Resource" : [for bucket in aws_s3_bucket.gitlab_object_stores : bucket.arn]
      }
    ]
  })
}

resource "aws_iam_role" "gitlab_object_stores" {
  name        = "GitlabS3Role-${var.deployment_name}"
  description = "Managed by Terraform. Role for GitLab to assume so that it can access relevant S3 buckets."
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

resource "aws_iam_role_policy_attachment" "gitlab_object_stores" {
  role       = aws_iam_role.gitlab_object_stores.name
  policy_arn = aws_iam_policy.gitlab_object_stores.arn
}


locals {
  connection_secret_name = "gitlab-s3-bucket-secrets"
  connection_secret_key = "connection"

  backups_secret_name = "gitlab-s3-backup-bucket-secrets"
  backups_secret_key = "config"
}

resource "kubectl_manifest" "gitlab_object_stores_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-s3-bucket-config
      namespace: gitlab
    data:
      values.yaml: |
        global:
          serviceAccount:
            create: true
            enabled: true
            annotations:
              eks.amazonaws.com/role-arn: ${aws_iam_role.gitlab_object_stores.arn}
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
        gitlab:
          toolbox:
            backups:
              objectStorage:
                config:
                  secret: ${local.backups_secret_name}
                  key: ${local.backups_secret_key}
  YAML
}

resource "kubectl_manifest" "gitlab_object_stores_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.connection_secret_name}
      namespace: gitlab
    stringData:
      ${local.connection_secret_key}: |
        provider: "AWS"
        use_iam_profile: "true"
        region: "${data.aws_region.current.name}"
  YAML
}

resource "kubectl_manifest" "gitlab_object_stores_backup_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.backups_secret_name}
      namespace: gitlab
    stringData:
      ${local.backups_secret_key}: |
        [default]
        bucket_location = ${data.aws_region.current.name}
  YAML
}
