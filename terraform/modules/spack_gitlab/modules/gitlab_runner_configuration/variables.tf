variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "protected_binary_bucket_arn" {
  description = "The ARN of the S3 bucket that contains protected binaries."
  type        = string
}

variable "pr_binary_bucket_arn" {
  description = "The ARN of the S3 bucket that contains PR binaries."
  type        = string
}

variable "gitlab_repo" {
  type = string
}
