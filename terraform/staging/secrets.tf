data "aws_secretsmanager_secret_version" "flux_github_token" {
  secret_id = "flux_github_token"
}

data "aws_secretsmanager_secret_version" "gitlab_token" {
  secret_id = "gitlab-terraform-provider-access-token"
}
