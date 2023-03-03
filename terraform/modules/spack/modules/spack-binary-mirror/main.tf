data "aws_canonical_user_id" "current" {}

resource "aws_s3_bucket" "spack_binary_mirror" {
  bucket              = "spack-binaries-prs${var.resource_suffix}"
  force_destroy       = false
  object_lock_enabled = false
}

resource "aws_s3_bucket_policy" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id
  policy = jsonencode({
    "Statement" : [
      {
        "Action" : "s3:GetObject",
        "Effect" : "Allow",
        "Principal" : "*",
        "Resource" : "${aws_s3_bucket.spack_binary_mirror.arn}/*",
        "Sid" : "PublicRead"
      }
    ],
    "Version" : "2012-10-17"
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id
  rule {
    id = "DeleteOldObjects${var.resource_suffix}"

    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 0
    }

    expiration {
      days                         = 14
      expired_object_delete_marker = false
    }
  }
}

resource "aws_s3_bucket_acl" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id
  access_control_policy {
    grant {
      grantee {
        id   = data.aws_canonical_user_id.current.id
        type = "CanonicalUser"
      }
      permission = "FULL_CONTROL"
    }

    grant {
      grantee {
        type = "Group"
        uri  = "http://acs.amazonaws.com/groups/global/AllUsers"
      }
      permission = "READ"
    }

    grant {
      grantee {
        type = "Group"
        uri  = "http://acs.amazonaws.com/groups/global/AllUsers"
      }
      permission = "READ_ACP"
    }

    owner {
      id = data.aws_canonical_user_id.current.id
    }
  }
}

resource "aws_s3_bucket_logging" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id

  # TODO: encode this "spack-logs" bucket into TF
  target_bucket = "spack-logs"
  target_prefix = "S3 Logs/"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_versioning" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id
  versioning_configuration {
    status     = "Disabled"
    mfa_delete = "Disabled"
  }
}

resource "aws_s3_bucket_request_payment_configuration" "spack_binary_mirror" {
  bucket = aws_s3_bucket.spack_binary_mirror.id
  payer  = "BucketOwner"
}
