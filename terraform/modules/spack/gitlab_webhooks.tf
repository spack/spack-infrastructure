locals {
  job_webhooks = ["http://gitlab-error-processor.custom.svc.cluster.local",
    "http://build-timing-processor.custom.svc.cluster.local",
  "http://webhook-handler.custom.svc.cluster.local"]
}


resource "gitlab_project_hook" "job_webhook" {
  for_each = toset(local.job_webhooks)

  project                 = data.gitlab_project.spack.id
  url                     = each.value
  job_events              = true
  push_events             = false
  enable_ssl_verification = false
}

// TODO: Once https://gitlab.com/gitlab-org/terraform-provider-gitlab/-/issues/1350 is resolved the
// gitlab_application_settings resource should be used to whitelist the domains in job_webhooks.


data "gitlab_user" "spackbot" {
  username = "spackbot"
}

resource "gitlab_personal_access_token" "webhook_handler" {
  user_id = data.gitlab_user.spackbot.id
  name    = "Webhook handler token"
  # TODO: How to deal with this expiring
  expires_at = "2024-12-03"

  scopes = ["read_api", "read_repository"]
}

resource "random_password" "webhook_handler" {
  length  = 64
  special = false
}

resource "kubectl_manifest" "webhook_secrets" {
  yaml_body = <<-YAML
     apiVersion: v1
     kind: Secret
     metadata:
       name: webhook-secrets
       namespace: custom
     data:
       gitlab-endpoint: ${base64encode("${var.gitlab_url}")}
       gitlab-token: ${base64encode("${gitlab_personal_access_token.webhook_handler.token}")}
       sentry-dsn: ${base64encode("${data.sentry_key.webhook_handler.dsn_public}")}
       secret-key: ${base64encode("${random_password.webhook_handler.result}")}
   YAML
}


resource "sentry_project" "webhook_handler" {
  organization = data.sentry_organization.default.id

  teams = [sentry_team.spack.id]
  name  = "Spack Webhook Handler"
  slug  = "spack-webhook-handler"

  platform = "python"
}

data "sentry_key" "webhook_handler" {
  organization = data.sentry_organization.default.id
  project      = sentry_project.webhook_handler.id
}
