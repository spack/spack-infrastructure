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
      }
    ]
  })
}

resource "aws_s3_bucket_logging" "binary_mirror" {
  count = var.enable_logging ? 1 : 0

  bucket = aws_s3_bucket.binary_mirror.id

  target_bucket = aws_s3_bucket.logging[0].id
  target_prefix = "S3 Logs/"
}
