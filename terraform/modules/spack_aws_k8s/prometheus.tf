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
            - name: OpenSearch
              editable: "false"
              type: grafana-opensearch-datasource
              url: "https://${aws_opensearch_domain.spack.endpoint}"
              version: "1"
              access: proxy
              basicAuth: "true"
              basicAuthUser: ${local.opensearch_master_user_name}
              secureJsonData:
                basicAuthPassword: "${random_password.opensearch_password.result}"
              jsonData:
                database: "gitlab-job-failures-*"
                timeField: timestamp
                flavor: opensearch
                version: "1.3.0"
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
            - name: AnalyticsDB
              type: postgres
              uid: XCh6DDkSz
              access: proxy
              url: ${module.analytics_db.db_instance_address}
              user: postgres
              database: analytics
              secureJsonData:
                password: "${random_password.analytics_db_password.result}"
              jsonData:
                postgresVersion: 15

  YAML
}
