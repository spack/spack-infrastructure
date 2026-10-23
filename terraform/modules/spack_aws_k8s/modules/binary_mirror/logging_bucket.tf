resource "aws_s3_bucket" "logging" {
  count = var.enable_logging ? 1 : 0

  bucket = var.logging_bucket_name

  tags = {
    Name = var.logging_bucket_name
  }
}

resource "aws_s3_bucket_policy" "logging" {
  count = var.enable_logging ? 1 : 0

  bucket = var.logging_bucket_name

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "Allow logging service to write to this bucket",
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "logging.s3.amazonaws.com"
        },
        "Action" : "s3:PutObject",
        "Resource" : "${aws_s3_bucket.logging[0].arn}/*"
      },
      {
        # CloudFront standard logging (v2) writes through CloudWatch vended logs.
        # Without this statement AWS appends an equivalent one itself, which the
        # next apply of this policy would then remove.
        "Sid" : "Allow CloudFront access log delivery",
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "delivery.logs.amazonaws.com"
        },
        "Action" : "s3:PutObject",
        "Resource" : "${aws_s3_bucket.logging[0].arn}/cloudfront/*",
        "Condition" : {
          "StringEquals" : {
            "s3:x-amz-acl" : "bucket-owner-full-control",
            "aws:SourceAccount" : data.aws_caller_identity.current.account_id
          },
          "ArnLike" : {
            "aws:SourceArn" : "arn:aws:logs:us-east-1:${data.aws_caller_identity.current.account_id}:delivery-source:*"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "logging" {
  count = var.enable_logging ? 1 : 0

  bucket = aws_s3_bucket.logging[0].id

  # Previously created by hand on spack-logs; managed here now so that adding
  # the CloudFront rule below doesn't wipe it out.
  rule {
    id     = "delete old spack-binaries-logs"
    status = "Enabled"

    filter {
      prefix = "spack-binaries-logs/"
    }

    expiration {
      days = 90
    }
  }

  # CloudFront access logs contain viewer IP addresses, so keep them only as
  # long as they're useful for traffic analysis.
  rule {
    id     = "delete old cloudfront logs"
    status = "Enabled"

    filter {
      prefix = "cloudfront/"
    }

    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket_logging" "binary_mirror" {
  count = var.enable_logging ? 1 : 0

  bucket = aws_s3_bucket.binary_mirror.id

  target_bucket = aws_s3_bucket.logging[0].id
  target_prefix = "S3 Logs/"
}
