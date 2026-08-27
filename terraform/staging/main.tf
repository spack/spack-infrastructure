module "spack_aws_k8s" {
  source = "../modules/spack_aws_k8s"

  deployment_name  = "staging"
  deployment_stage = "blue"

  region = "us-west-2"

  enable_analytics_db = false

  gitlab_db_instance_class    = "db.t4g.small"
  gitlab_redis_instance_class = "cache.t4g.small"

  cdash_db_instance_class = "db.t4g.small"
}

module "spack_flux" {
  source = "../modules/spack_flux"

  flux_path = "k8s/staging/"

  deployment_name  = "staging"
  deployment_stage = "blue"

  region = "us-west-2"

  nat_public_ips = module.spack_aws_k8s.nat_public_ips
}

module "spack_gitlab" {
  source = "../modules/spack_gitlab"

  deployment_name  = "staging"
  deployment_stage = "blue"

  region = "us-west-2"

  gitlab_token   = var.gitlab_token
  nat_public_ips = module.spack_aws_k8s.nat_public_ips
}
