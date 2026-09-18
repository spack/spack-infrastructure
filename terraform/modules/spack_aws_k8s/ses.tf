locals {
  ses_email_domain = "${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
}

resource "aws_ses_domain_identity" "ses_domain_identity" {
  domain = local.ses_email_domain
}

resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = "_amazonses.${local.ses_email_domain}"
  type    = "TXT"
  ttl     = "600"
  records = [aws_ses_domain_identity.ses_domain_identity.verification_token]
}

locals {
  ses_vdm_configuration_set_name = "spack-gitlab-vdm${local.suffix}"
}

resource "aws_sesv2_configuration_set" "vdm" {
  configuration_set_name = local.ses_vdm_configuration_set_name

  vdm_options {
    dashboard_options {
      engagement_metrics = "ENABLED"
    }
  }
}

resource "aws_sesv2_email_identity" "ses_domain_identity_vdm" {
  email_identity         = aws_ses_domain_identity.ses_domain_identity.domain
  configuration_set_name = aws_sesv2_configuration_set.vdm.configuration_set_name
}

resource "aws_iam_user" "ses_user" {
  name = "ses-smtp-user-${var.deployment_name}-${var.deployment_stage}"
}

resource "aws_iam_access_key" "ses_user" {
  user = aws_iam_user.ses_user.name
}

resource "aws_iam_user_policy" "ses_user" {
  name = "AmazonSesSendingAccess"
  user = aws_iam_user.ses_user.name

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "ses:SendRawEmail",
        "Resource" : "*"
      }
    ]
  })
}

locals {
  gitlab_email_domain             = "gitlab.${local.ses_email_domain}"
  gitlab_smtp_secret_name         = "gitlab-ses-secrets"
  gitlab_smtp_secret_password_key = "smtp-password"
}

resource "kubectl_manifest" "ses_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-ses-config
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    data:
      values.yaml: |
        global:
          email:
            from: admin@${local.gitlab_email_domain}
            reply_to: noreply@${local.gitlab_email_domain}
          smtp:
            enabled: true
            address: email-smtp.${data.aws_region.current.region}.amazonaws.com
            user_name: ${aws_iam_access_key.ses_user.id}
            password:
              secret: ${local.gitlab_smtp_secret_name}
              key: ${local.gitlab_smtp_secret_password_key}
            port: 465
            tls: true
  YAML
}

resource "kubectl_manifest" "ses_secrets" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.gitlab_smtp_secret_name}
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    data:
      ${local.gitlab_smtp_secret_password_key}: ${base64encode("${aws_iam_access_key.ses_user.ses_smtp_password_v4}")}
  YAML
}


# SMTP credentials used by Metabase to send email through SES. Metabase is only
# deployed in production, and the IAM user name is account-global, so this is
# gated to the prod deployment.
resource "aws_iam_user" "metabase_ses_smtp_user" {
  count = var.deployment_name == "prod" ? 1 : 0

  name = "metabase-ses-smtp-user.20230503-153955"
}

resource "aws_iam_user_policy" "metabase_ses_sending_access" {
  count = var.deployment_name == "prod" ? 1 : 0

  name = "AmazonSesSendingAccess"
  user = aws_iam_user.metabase_ses_smtp_user[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ses:SendRawEmail"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_access_key" "metabase_ses_smtp_user" {
  count = var.deployment_name == "prod" ? 1 : 0

  user = aws_iam_user.metabase_ses_smtp_user[0].name
}

locals {
  metabase_email_domain             = "metabase.${local.ses_email_domain}"
  metabase_smtp_secret_name         = "metabase-ses-secrets"
  metabase_smtp_secret_password_key = "smtp-password"
}

resource "kubectl_manifest" "metabase_ses_config_map" {
  count = var.deployment_name == "prod" ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: metabase-ses-config
      namespace: monitoring
    data:
      MB_EMAIL_FROM_ADDRESS: admin@${local.metabase_email_domain}
      MB_EMAIL_REPLY_TO: '["noreply@${local.metabase_email_domain}"]'
      MB_EMAIL_SMTP_HOST: email-smtp.${data.aws_region.current.region}.amazonaws.com
      MB_EMAIL_SMTP_USERNAME: ${aws_iam_access_key.metabase_ses_smtp_user[0].id}
      MB_EMAIL_SMTP_PORT: "465"
      MB_EMAIL_SMTP_SECURITY: ssl
  YAML
}

resource "kubectl_manifest" "metabase_ses_secrets" {
  count = var.deployment_name == "prod" ? 1 : 0

  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: ${local.metabase_smtp_secret_name}
      namespace: monitoring
    data:
      ${local.metabase_smtp_secret_password_key}: ${base64encode("${aws_iam_access_key.metabase_ses_smtp_user[0].ses_smtp_password_v4}")}
  YAML
}
