module "spack_aws_k8s" {
  source = "../modules/spack_aws_k8s"

  deployment_name  = "prod"
  deployment_stage = "blue"

  region           = "us-east-1"
  eks_cluster_role = var.eks_cluster_role

  flux_path = "k8s/production/"

  gitlab_db_instance_class    = "db.t3.xlarge"
  gitlab_redis_instance_class = "cache.m6g.xlarge"
  cdash_db_instance_class     = "db.m6g.large"
  opensearch_instance_type    = "r6g.xlarge.search"
  opensearch_volume_size      = 500
}

module "spack_gitlab" {
  source = "../modules/spack_gitlab"

  deployment_name  = "prod"
  deployment_stage = "blue"

  region = "us-east-1"

  gitlab_token = var.gitlab_token
}
