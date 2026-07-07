output "bucket_name" {
  description = "The name of the binary mirror S3 bucket."
  value       = aws_s3_bucket.binary_mirror.id
}

output "bucket_arn" {
  description = "The ARN of the binary mirror S3 bucket."
  value       = aws_s3_bucket.binary_mirror.arn
}

output "logging_bucket_arn" {
  description = "The ARN of the S3 logging bucket (empty string if logging is disabled)."
  value       = var.enable_logging ? aws_s3_bucket.logging[0].arn : ""
}
