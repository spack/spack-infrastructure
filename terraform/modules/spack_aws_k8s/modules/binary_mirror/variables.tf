variable "bucket_name" {
  description = "The name of the S3 bucket."
  type        = string
}

variable "logging_bucket_name" {
  description = "The name of the S3 bucket that receives this mirror's logs. Its policy must allow both S3 server access logging and CloudFront log delivery under cloudfront/."
  type        = string
}

variable "enable_s3_access_logging" {
  description = "Whether or not S3 server access logs for this bucket are delivered to the logging bucket."
  type        = bool
}

variable "enable_cloudfront_logging" {
  description = "Whether or not CloudFront access logs are delivered to the logging bucket, under the cloudfront/ prefix."
  type        = bool
  default     = false
}

variable "cdn_domain" {
  description = "The domain name of the CDN that points to the bucket."
  type        = string
}

variable "cache_policy_id" {
  description = "The ID of the cache policy to use for this bucket."
  type        = string
}
