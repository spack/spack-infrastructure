locals {
  spackbot_token_expires_at = "2025-04-25"
}

resource "gitlab_personal_access_token" "spackbot" {
  user_id    = data.gitlab_user.spackbot.id
  name       = "spackbot personal access token"
  expires_at = local.spackbot_token_expires_at

  scopes = ["api"]

  lifecycle {
    precondition {
      condition     = timecmp(timestamp(), "${local.spackbot_token_expires_at}T00:00:00Z") == -1
      error_message = "The token has expired. Please update the expires_at date."
    }
  }
}

resource "kubectl_manifest" "spackbot_gitlab_credentials" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: spack-bot-gitlab-credentials
      namespace: spack
    data:
      gitlab_token: ${base64encode("${gitlab_personal_access_token.spackbot.token}")}
  YAML
}
