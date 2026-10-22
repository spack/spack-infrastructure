variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "region" {
  type = string
}

variable "nat_public_ips" {
  type = list(string)
}

variable "flux_path" {
  description = "Path relative to the repository root that Flux will use to sync resources"
  type        = string
}
