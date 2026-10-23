# Bucket that receives access logs for the binary mirrors (S3 server access
# logs and CloudFront access logs), as well as buildcache pruning output.
resource "aws_s3_bucket" "logs" {
  bucket = "spack-logs${local.bucket_name_suffix}"

  tags = {
    Name = "spack-logs${local.bucket_name_suffix}"
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id

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
        "Resource" : "${aws_s3_bucket.logs.arn}/*"
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
        "Resource" : "${aws_s3_bucket.logs.arn}/cloudfront/*",
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

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

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
