variable "deployment_name" {
  description = "Name of this deployment environment, for example 'production', 'staging', etc."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
}

variable "public_subnets" {
  description = "List of public subnets to create inside the VPC"
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

variable "kubernetes_version" {
  description = "The version of kubernetes to run on the EKS cluster."
  type        = string
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

variable "flux_target_path" {
  description = "Path to directory for Flux to watch within the git repo."
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

variable "gitlab_db_master_credentials_secret" {
  description = "The arn to the secret in Secrets Manager for the gitlab RDS instance."
  type        = string
}


variable "provision_opensearch_cluster" {
  description = "Whether or not to provision an OpenSearch cluster for this deployment."
  type        = bool
}

variable "ses_email_domain" {
  description = "Domain to use for SES email."
  type = string
}
