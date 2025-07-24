data "aws_secretsmanager_secret_version" "flux_github_token" {
  secret_id = "flux_github_token"
}
