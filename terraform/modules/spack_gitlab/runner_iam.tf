data "aws_s3_bucket" "protected_mirror" {
  bucket = "spack-binaries${local.suffix}"
}

data "aws_s3_bucket" "pr_mirror" {
  bucket = "spack-binaries-prs${local.suffix}"
}

module "spack_project_runner_configuration" {
  source = "./modules/gitlab_runner_configuration"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  pr_binary_bucket_arn        = data.aws_s3_bucket.pr_mirror.arn
  protected_binary_bucket_arn = data.aws_s3_bucket.protected_mirror.arn

  gitlab_repo = data.gitlab_project.spack.path_with_namespace
}
