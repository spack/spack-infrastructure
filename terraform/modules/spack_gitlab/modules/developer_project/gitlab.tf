data "gitlab_project" "this" {
  path_with_namespace = var.gitlab_repo
}

module "gitlab_runner_configuration" {
  source = "../gitlab_runner_configuration"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  pr_binary_bucket_arn        = module.pr_binary_mirror.bucket_arn
  protected_binary_bucket_arn = module.protected_binary_mirror.bucket_arn

  gitlab_repo = data.gitlab_project.this.path_with_namespace
}
