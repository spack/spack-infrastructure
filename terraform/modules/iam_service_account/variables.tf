variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "service_account_name" {
  description = "The name of the service account"
  type        = string
}

variable "service_account_namespace" {
  description = "The namespace of the service account"
  type        = string
}

variable "service_account_iam_policies" {
  description = "The IAM policy to attach to the service account"
  type        = list(string)
}

variable "service_account_iam_role_description" {
  description = "The description of the IAM role"
  type        = string
  default     = ""
}
