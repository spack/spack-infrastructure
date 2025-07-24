variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "region" {
  type = string
}

variable "flux_path" {
  description = "Path relative to the repository root that Flux will use to sync resources"
  type        = string
}

variable "gitlab_db_instance_class" {
  description = "AWS RDS DB instance class for the Spack GitLab PostgreSQL database."
  type        = string
}

variable "gitlab_redis_instance_class" {
  description = "AWS ElastiCache instance class for the Spack GitLab redis instance."
  type        = string
}

variable "cdash_db_instance_class" {
  description = "AWS RDS DB instance class for the Spack CDash PostgreSQL database."
  type        = string
}

variable "opensearch_instance_type" {
  description = "The instance type for the OpenSearch domain."
  type        = string
}

variable "opensearch_volume_size" {
  description = "The size of the EBS volume for the OpenSearch domain."
  type        = number
}

variable "eks_cluster_role" {
  description = "The IAM role to assume when interacting with EKS resources."
  type        = string
  default     = null
}
