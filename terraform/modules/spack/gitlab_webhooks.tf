locals {
  job_webhooks = ["http://gitlab-error-processor.custom.svc.cluster.local",
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

data "aws_secretsmanager_secret_version" "gitlab_db_ro_credentials" {
  secret_id = "gitlab-${var.deployment_name}-readonly-credentials"
}

# Note: the /1 is important to ensure that the broker for the webhook handler isn't using the same
# database as the broker for spackbot.
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
       gitlab-db-user: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["username"]}")}
       gitlab-db-host: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["host"]}")}
       gitlab-db-port: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["port"]}")}
       gitlab-db-name: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["dbname"]}")}
       gitlab-db-password: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["password"]}")}
       sentry-dsn: ${base64encode("${local.sentry_dsns["webhook-handler"]}")}
       secret-key: ${base64encode("${random_password.webhook_handler.result}")}
       celery-broker-url: ${base64encode("redis://${aws_elasticache_replication_group.pr_binary_graduation_task_queue.primary_endpoint_address}:6379/1")}
   YAML
}
