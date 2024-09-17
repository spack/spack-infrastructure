variable "deployment_name" {
  description = "Name of this deployment environment, for example 'production', 'staging', etc."
  type        = string
}

variable "gitlab_url" {
  description = "URL of the GitLab server."
  type        = string
}

variable "github_actions_oidc_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
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

variable "analytics_db_credentials_secret" {
  description = "The arn to the secret in Secrets Manager for the analytics RDS instance."
  type        = string
}

variable "opensearch_instance_type" {
  description = "AWS OpenSearch instance type for the Spack OpenSearch cluster."
  type        = string
}

variable "opensearch_volume_size" {
  description = "AWS OpenSearch volume size for the Spack OpenSearch cluster."
  type        = string
}

variable "ses_email_domain" {
  description = "Domain to use for SES email."
  type        = string
}

variable "elasticache_instance_class" {
  description = "AWS ElastiCache instance class for the Spack GitLab redis instance."
  type        = string
}
