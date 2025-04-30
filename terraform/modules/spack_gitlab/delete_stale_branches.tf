locals {
  delete_stale_branches_token_expires_at = "2026-04-25"
}

resource "gitlab_personal_access_token" "delete_stale_branches" {
  user_id    = data.gitlab_user.spackbot.id
  name       = "delete-stale-branches cronjob personal access token."
  expires_at = local.delete_stale_branches_token_expires_at

  scopes = ["api"]

  lifecycle {
    precondition {
      condition     = timecmp(timestamp(), "${local.delete_stale_branches_token_expires_at}T00:00:00Z") == -1
      error_message = "The token has expired. Please update the expires_at date."
    }
  }
}

resource "kubectl_manifest" "delete_stale_branches" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: delete-stale-branches-credentials
      namespace: custom
    data:
      gitlab-token: ${base64encode("${gitlab_personal_access_token.delete_stale_branches.token}")}
  YAML
}
