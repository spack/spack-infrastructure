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
