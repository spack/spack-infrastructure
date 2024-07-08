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
