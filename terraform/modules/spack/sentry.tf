data "aws_secretsmanager_secret_version" "sentry_dsn" {
  secret_id = "sentry-dsn-${var.deployment_name}"
}

locals {
  sentry_dsns = jsondecode(data.aws_secretsmanager_secret_version.sentry_dsn.secret_string)
}

resource "kubectl_manifest" "gitlab_runner_sentry_config_map" {
  count = var.deployment_name == "prod" ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-runner-sentry-config
      namespace: gitlab
    data:
      values.yaml: |
        sentryDsn: ${local.sentry_dsns["gitlab-runner"]}
  YAML
}

resource "kubectl_manifest" "gh_gl_sync_sentry_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gh-gl-sync-sentry-config
      namespace: custom
    data:
      SENTRY_DSN: "${local.sentry_dsns["gh-gl-sync"]}"
      SENTRY_ENVIRONMENT: "${var.deployment_name}"
  YAML
}

resource "kubectl_manifest" "python_scripts_sentry_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: python-scripts-sentry-config
      namespace: custom
    data:
      SENTRY_DSN: "${local.sentry_dsns["python-scripts"]}"
      SENTRY_ENVIRONMENT: "${var.deployment_name}"
  YAML
}
