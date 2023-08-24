resource "aws_iam_user" "pr_binaries_bucket" {
  name = "pull-requests-binary-mirror${var.binary_mirror_bucket_suffix}"
}

resource "aws_s3_bucket" "pr_binaries_bucket" {
  bucket = "spack-binaries-prs${var.binary_mirror_bucket_suffix}"

  tags = {
    Name = "spack-binaries-prs${var.binary_mirror_bucket_suffix}"
  }
}

resource "aws_s3_bucket_policy" "pr_binaries_bucket" {
  # Only create this bucket policy if binary mirrors are allowed to be public
  count = var.public_binary_mirrors ? 1 : 0

  bucket = aws_s3_bucket.pr_binaries_bucket.id

  policy = jsonencode({
    Statement = [
      {
        Sid       = "PublicRead"
        Action    = "s3:GetObject"
        Effect    = "Allow"
        Principal = "*"
        Resource  = "${aws_s3_bucket.pr_binaries_bucket.arn}/*"
      }
    ]
    Version = "2012-10-17"
  })
}

resource "aws_s3_bucket_acl" "pr_binaries_bucket" {
  # Only create this bucket policy if binary mirrors are allowed to be public
  count = var.public_binary_mirrors ? 1 : 0

  bucket = aws_s3_bucket.pr_binaries_bucket.id

  access_control_policy {
    owner {
      id = data.aws_canonical_user_id.current.id
    }
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
  }
}

resource "aws_s3_bucket_versioning" "pr_binaries_bucket" {
  bucket = aws_s3_bucket.pr_binaries_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pr_binaries_bucket" {
  bucket = aws_s3_bucket.pr_binaries_bucket.id

  rule {
    bucket_key_enabled = false

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_logging" "pr_binaries_bucket" {
  bucket = aws_s3_bucket.pr_binaries_bucket.id

  target_bucket = "spack-logs"
  target_prefix = "S3 Logs/"
}

resource "aws_s3_bucket_lifecycle_configuration" "pr_binaries_bucket" {
  bucket = aws_s3_bucket.pr_binaries_bucket.id

  rule {
    id = "DeleteOldObjects"

    expiration {
      days                         = 14
      expired_object_delete_marker = false
    }

    status = "Disabled"
  }
}
