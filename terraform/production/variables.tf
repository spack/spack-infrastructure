variable "gitlab_token" {
  description = "The GitLab token to use for authentication"
  type        = string
  sensitive   = true
}

variable "eks_cluster_role" {
  description = "The IAM role to assume when interacting with EKS resources."
  type        = string
  default     = null
}

variable "aws_assume_role_arn" {
  description = "The IAM role ARN for the AWS provider to assume."
  type        = string
  default     = "arn:aws:iam::588562868276:role/terraform-role"
}
