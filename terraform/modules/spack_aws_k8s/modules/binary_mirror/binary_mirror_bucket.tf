resource "aws_iam_user" "binary_mirror" {
  name = var.bucket_iam_username
}

resource "aws_s3_bucket" "binary_mirror" {
  bucket = var.bucket_name

  tags = {
    Name = var.bucket_name
  }
}

resource "aws_s3_bucket_policy" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  policy = jsonencode({
    Statement = [
      {
        Sid       = "PublicRead"
        Action    = "s3:GetObject"
        Effect    = "Allow"
        Principal = "*"
        Resource  = "${aws_s3_bucket.binary_mirror.arn}/*"
      }
    ]
    Version = "2012-10-17"
  })

  depends_on = [
    aws_s3_bucket_public_access_block.binary_mirror,
    aws_s3_bucket_ownership_controls.binary_mirror,
  ]
}

resource "aws_s3_bucket_versioning" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  rule {
    id     = "Delete non-current versions after 30 days"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    expiration {
      expired_object_delete_marker = true
    }
  }
}

resource "aws_s3_bucket_acl" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

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

  depends_on = [
    aws_s3_bucket_public_access_block.binary_mirror,
    aws_s3_bucket_ownership_controls.binary_mirror,
  ]
}

resource "aws_s3_bucket_public_access_block" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_ownership_controls" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  rule {
    object_ownership = "ObjectWriter"
  }
}
