variable "deployment_name" {
  description = "The name of the deployment. This will be used as a prefix for all resources."
  type        = string
}

variable "protected_binary_bucket_arn" {
  description = "The ARN of the S3 bucket that contains protected binaries."
  type        = string
}

variable "pr_binary_bucket_arn" {
  description = "The ARN of the S3 bucket that contains PR binaries."
  type        = string
}
