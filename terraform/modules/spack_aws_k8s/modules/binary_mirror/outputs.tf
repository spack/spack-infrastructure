output "bucket_name" {
  description = "The name of the binary mirror S3 bucket."
  value       = aws_s3_bucket.binary_mirror.id
}

output "bucket_arn" {
  description = "The ARN of the binary mirror S3 bucket."
  value       = aws_s3_bucket.binary_mirror.arn
}
