variable "deployment_name" {
  type = string
}

variable "deployment_stage" {
  type = string
}

variable "region" {
  type = string
}

variable "analytics_db_instance_class" {
  description = "AWS RDS DB instance class for the analytics PostgreSQL database."
  type        = string
  default     = "db.t4g.xlarge"
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

variable "eks_cluster_role" {
  description = "The IAM role to assume when interacting with EKS resources."
  type        = string
  default     = null
}
