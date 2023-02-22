variable "deployment_name" {
  description = "Name of this deployment environment, for example 'production', 'staging', etc."
  type        = string
}

variable "single_nat_gateway" {
  description = "Should be true if you want to provision a single shared NAT Gateway across all of your private networks."
  type        = bool
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
}

variable "public_subnets" {
  description = "List of public subnets to create inside the VPC"
  type        = list(string)
}

variable "database_subnets" {
  description = "List of database subnets to create inside the VPC"
  type        = list(string)
}

variable "private_subnets" {
  description = "List of private subnets to create inside the VPC"
  type        = list(string)
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
}

variable "flux_repo_name" {
  description = "Name of GitHub repo to configure Flux with."
  type        = string
}

variable "flux_repo_owner" {
  description = "Owner (user or org) of GitHub repo to configure Flux with."
  type        = string
}

variable "flux_branch" {
  description = "Git branch to configure Flux with."
  type        = string
}

variable "cdash_db_instance_class" {
  description = "AWS RDS DB instance class for the Spack CDash MySQL database."
  type        = string
}

variable "gitlab_db_instance_class" {
  description = "AWS RDS DB instance class for the Spack GitLab PostgreSQL database."
  type        = string
}
