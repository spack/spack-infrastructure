resource "gitlab_project_hook" "job_webhook" {
  project                 = data.gitlab_project.spack_packages.id
  url                     = "http://webhook-handler.custom.svc.cluster.local"
  job_events              = true
  push_events             = false
  enable_ssl_verification = false
}

// TODO: Once https://gitlab.com/gitlab-org/terraform-provider-gitlab/-/issues/1350 is resolved the
// gitlab_application_settings resource should be used to whitelist the domains in job_webhooks.

module "webhook_handler_token" {
  source = "./modules/spackbot_personal_access_token"

  name   = "Webhook handler token"
  scopes = ["api"]
}

resource "random_password" "webhook_handler" {
  length  = 64
  special = false
}

data "aws_secretsmanager_secret_version" "gitlab_db_ro_credentials" {
  secret_id = "gitlab-${var.deployment_name}-readonly-credentials"
}

data "aws_secretsmanager_secret_version" "sentry_dsn" {
  secret_id = "sentry-dsn-${var.deployment_name}"
}

locals {
  sentry_dsns = jsondecode(data.aws_secretsmanager_secret_version.sentry_dsn.secret_string)
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
       gitlab-endpoint: ${base64encode("${local.gitlab_url}")}
       gitlab-token: ${base64encode("${module.webhook_handler_token.token}")}
       gitlab-db-user: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["username"]}")}
       gitlab-db-host: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["host"]}")}
       gitlab-db-port: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["port"]}")}
       gitlab-db-name: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["dbname"]}")}
       gitlab-db-password: ${base64encode("${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["password"]}")}
       sentry-dsn: ${base64encode("${local.sentry_dsns["webhook-handler"]}")}
       secret-key: ${base64encode("${random_password.webhook_handler.result}")}
       celery-broker-url: ${base64encode("redis://${data.aws_elasticache_replication_group.spackbot_queue.primary_endpoint_address}:6379/1")}
   YAML
}
