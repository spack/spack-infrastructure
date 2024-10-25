variable "bucket_name" {
  description = "The name of the S3 bucket."
  type        = string
}

variable "bucket_iam_username" {
  description = "Username for IAM user that has write access to this bucket."
  type        = string
}

variable "enable_logging" {
  description = "Whether or not this bucket has logging enabled."
  type        = bool
}

variable "logging_bucket_name" {
  description = "The name of the S3 bucket used for logging."
  type        = string
  default     = null
}

variable "cdn_domain" {
  description = "The domain name of the CDN that points to the bucket."
  type        = string
}

variable "cache_policy_id" {
  description = "The ID of the cache policy to use for this bucket."
  type        = string
}
