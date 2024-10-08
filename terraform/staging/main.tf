module "spack_aws_k8s" {
  source = "../modules/spack_aws_k8s"

  deployment_name  = "staging"
  deployment_stage = "blue"

  region = "us-west-2"

  flux_path = "k8s/staging/"

  gitlab_db_instance_class    = "db.t3.small"
  gitlab_redis_instance_class = "cache.t4g.small"
  cdash_db_instance_class     = "db.t3.small"
  opensearch_instance_type    = "t3.small.search"
  opensearch_volume_size      = 100
}

module "spack_gitlab" {
  source = "../modules/spack_gitlab"

  deployment_name  = "staging"
  deployment_stage = "blue"

  region = "us-west-2"

  gitlab_token = var.gitlab_token
}
