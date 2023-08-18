resource "aws_ses_domain_identity" "ses_domain_identity" {
  domain = var.ses_email_domain
}

resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = "_amazonses.${var.ses_email_domain}"
  type    = "TXT"
  ttl     = "600"
  records = [aws_ses_domain_identity.ses_domain_identity.verification_token]
}

resource "aws_iam_user" "ses_user" {
  name = "ses-smtp-user-${var.deployment_name}"
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
            reply_to: noreplay@${local.gitlab_email_domain}
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

# resource "kubectl_manifest" "ses_sentry_config_map" {
#   yaml_body = <<-YAML
#     apiVersion: v1
#     kind: ConfigMap
#     metadata:
#       name: sentry-ses-config
#       namespace: sentry
#     data:
#       values.yaml: |
#         mail:
#           # For example: smtp
#           backend: smtp
#           useTls: true
#           useSsl: false
#           username: "${aws_iam_access_key.ses_user.id}"
#           password: "${aws_iam_access_key.ses_user.ses_smtp_password_v4}"
#           port: 65
#           host: sentry.${var.ses_email_domain}
#           from: admin@sentry.${var.ses_email_domain}
#   YAML
# }
