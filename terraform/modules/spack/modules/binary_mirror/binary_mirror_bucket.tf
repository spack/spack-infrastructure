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
  # Only create this bucket policy if binary mirrors are allowed to be public
  count = var.public ? 1 : 0

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
}

resource "aws_s3_bucket_versioning" "binary_mirror" {
  bucket = aws_s3_bucket.binary_mirror.id

  versioning_configuration {
    status = "Enabled"
  }
}


resource "aws_s3_bucket_acl" "binary_mirror" {
  # Only create this bucket policy if binary mirrors are allowed to be public
  count = var.public ? 1 : 0

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
}
