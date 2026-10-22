data "aws_secretsmanager_secret_version" "gitlab_db_ro_credentials" {
  secret_id = "gitlab-${var.deployment_name}-readonly-credentials"
}

resource "kubectl_manifest" "prometheus_additional_datasources_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: grafana-additional-datasources
      namespace: monitoring
    stringData:
      values.yaml: |-
        grafana:
          additionalDataSources:
            - name: PostgreSQL
              type: postgres
              access: proxy
              url: ${module.gitlab_db.db_instance_address}
              user: ${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["username"]}
              database: gitlabhq_production
              secureJsonData:
                password: "${jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_ro_credentials.secret_string)["password"]}"
              jsonData:
                postgresVersion: 14
  YAML
}
