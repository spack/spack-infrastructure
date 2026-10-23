# Bucket that receives S3 server access logs for the binary mirrors, as well
# as buildcache pruning output.
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
      }
    ]
  })
}

# These resources used to live in the pr_binary_mirror module.
moved {
  from = module.pr_binary_mirror.aws_s3_bucket.logging[0]
  to   = aws_s3_bucket.logs
}

moved {
  from = module.pr_binary_mirror.aws_s3_bucket_policy.logging[0]
  to   = aws_s3_bucket_policy.logs
}
