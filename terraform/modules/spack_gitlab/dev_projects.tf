module "mike_dev_project" {
  source = "./modules/developer_project"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  gitlab_repo = "mvandenburgh/spack"
}
