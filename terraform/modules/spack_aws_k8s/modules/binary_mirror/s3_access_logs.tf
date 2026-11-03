resource "aws_s3_bucket_logging" "binary_mirror" {
  count = var.enable_s3_access_logging ? 1 : 0

  bucket = aws_s3_bucket.binary_mirror.id

  target_bucket = var.logging_bucket_name
  target_prefix = "S3 Logs/"
}
