data "gitlab_project" "this" {
  path_with_namespace = var.gitlab_repo
}

resource "gitlab_project_variable" "binary_mirror_role_arn" {
  for_each = resource.aws_iam_role.gitlab_runner

  project = data.gitlab_project.this.id
  key     = local.mirror_roles[each.key].role_arn_ci_var_name
  value   = each.value.arn
}

# pre_build.py needs access to this to request PR prefix scoped permissions
resource "gitlab_project_variable" "pr_binary_mirror_bucket_arn" {
  project = data.gitlab_project.this.id
  key     = "PR_BINARY_MIRROR_BUCKET_ARN"
  value   = var.pr_binary_bucket_arn
}

# Configure retries
resource "gitlab_project_variable" "retries" {
  for_each = toset([
    # Enable retries for artifact downloads, source fetching, and cache restoration in CI jobs
    "ARTIFACT_DOWNLOAD_ATTEMPTS",
    "GET_SOURCES_ATTEMPTS",
    "RESTORE_CACHE_ATTEMPTS",
  ])

  project = data.gitlab_project.this.id
  key     = each.value
  value   = "3"
}
