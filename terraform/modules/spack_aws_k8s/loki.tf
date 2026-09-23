# Object storage for Loki (k8s/production/loki/), which stores pod logs and
# Kubernetes events shipped by Alloy (k8s/production/alloy/).
resource "aws_s3_bucket" "loki" {
  bucket = "spack-loki${local.bucket_name_suffix}"
}

resource "aws_s3_bucket_public_access_block" "loki" {
  bucket = aws_s3_bucket.loki.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Retention is enforced by the Loki compactor (limits_config.retention_period,
# currently 30 days). This is only a backstop in case compactor retention ever
# stops working, so the bucket can't grow unbounded unnoticed.
resource "aws_s3_bucket_lifecycle_configuration" "loki" {
  bucket = aws_s3_bucket.loki.id

  # Chunks are stored under the tenant ID, which is "fake" when auth is disabled.
  rule {
    id = "ExpireChunksOlderThan60Days"

    filter {
      prefix = "fake/"
    }

    expiration {
      days = 60 # per LLNL policy
    }

    status = "Enabled"
  }

  rule {
    id = "ExpireIndexOlderThan60Days"

    filter {
      prefix = "index/"
    }

    expiration {
      days = 60 # per LLNL policy
    }

    status = "Enabled"
  }

  rule {
    id = "AbortIncompleteMultipartUploads"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    status = "Enabled"
  }
}

module "loki" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:ListBucket",
          "Resource" : aws_s3_bucket.loki.arn
        },
        {
          "Effect" : "Allow",
          "Action" : [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject"
          ],
          "Resource" : "${aws_s3_bucket.loki.arn}/*"
        }
      ]
    })
  ]
  service_account_name                 = "loki"
  service_account_namespace            = "monitoring"
  service_account_iam_role_description = "Read/write access to the Loki S3 bucket."
}
