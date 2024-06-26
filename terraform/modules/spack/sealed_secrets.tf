resource "aws_s3_bucket" "sealed_secret_key_pairs" {
  bucket = "spack-${var.deployment_name}-sealed-secret-key-pairs"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "sealed_secret_key_pairs" {
  bucket = aws_s3_bucket.sealed_secret_key_pairs.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Bucket policy that prevents any public access
resource "aws_s3_bucket_policy" "sealed_secret_key_pairs" {
  bucket = aws_s3_bucket.sealed_secret_key_pairs.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Principal" : "*"
        "Effect" : "Deny",
        "Action" : "*",
        "Resource" : "${aws_s3_bucket.sealed_secret_key_pairs.arn}",
      }
    ]
  })
}

resource "aws_iam_policy" "sealed_secret_key_pairs" {
  name        = "SealedSecretS3Role-${var.deployment_name}"
  description = "Managed by Terraform. Grants required permissions to read/write to sealed-secret backup bucket."

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:*",
        "Resource" : "${aws_s3_bucket.sealed_secret_key_pairs.arn}",
      },
    ]
  })
}

resource "aws_iam_role" "sealed_secret_key_pairs" {
  name        = "SealedSecretS3Role-${var.deployment_name}"
  description = "Managed by Terraform. Role to assume to access relevant S3 buckets."
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

resource "aws_iam_role_policy_attachment" "sealed_secret_key_pairs" {
  role       = aws_iam_role.sealed_secret_key_pairs.name
  policy_arn = aws_iam_policy.sealed_secret_key_pairs.arn
}


# The ServiceAccount to be used by the backup job
resource "kubectl_manifest" "sealed_secret_key_pair_backup" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: sealed-secret-backup
      namespace: custom
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.sealed_secret_key_pairs.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.sealed_secret_key_pairs
  ]
}
