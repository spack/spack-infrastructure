resource "kubectl_manifest" "gitlab_runner_sentry_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-runner-sentry-config
      namespace: gitlab
    data:
      values.yaml: |
        sentryDsn: ${data.sentry_key.gitlab_runner.dsn_public}
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
      SENTRY_DSN: ${data.sentry_key.gh_gl_sync.dsn_public}
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
      SENTRY_DSN: ${data.sentry_key.python_scripts.dsn_public}
  YAML
}
