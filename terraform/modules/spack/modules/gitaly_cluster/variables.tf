variable "deployment_name" {
  description = "Name of this deployment environment, for example 'production', 'staging', etc."
  type        = string
}

variable "vpc_id" {
  description = "The VPC ID."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
}

variable "db_subnet_ids" {
  type = list(string)
}
