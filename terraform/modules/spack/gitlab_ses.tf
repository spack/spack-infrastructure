locals {
  gitlab_email_domain = "gitlab.${var.ses_email_domain}"
  smtp_secret_name = "gitlab-ses-secrets"
  smtp_secret_password_key = "smtp-password"
}

resource "kubectl_manifest" "ses_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-ses-config
      namespace: gitlab
    data:
      values.yaml: |
        global:
          email:
            from: admin@${local.gitlab_email_domain}
            reply_to: noreply@${local.gitlab_email_domain}
          smtp:
            enabled: true
            address: email-smtp.${data.aws_region.current.name}.amazonaws.com
            user_name: ${aws_iam_access_key.ses_user.id}
            password:
              secret: ${local.smtp_secret_name}
              key: ${local.smtp_secret_password_key}
            port: 465
            tls: true
  YAML
}

resource "kubectl_manifest" "ses_secrets" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.smtp_secret_name}
      namespace: gitlab
    data:
      ${local.smtp_secret_password_key}: ${base64encode("${aws_iam_access_key.ses_user.ses_smtp_password_v4}")}
  YAML
}
