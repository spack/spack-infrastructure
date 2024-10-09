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
