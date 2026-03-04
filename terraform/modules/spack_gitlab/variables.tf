variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "region" {
  type = string
}

variable "gitlab_token" {
  description = "The GitLab token to use for authentication"
  type        = string
  sensitive   = true
}

variable "aws_assume_role_arn" {
  description = "The IAM role ARN for the AWS provider to assume."
  type        = string
  default     = "arn:aws:iam::588562868276:role/terraform-role"
}
