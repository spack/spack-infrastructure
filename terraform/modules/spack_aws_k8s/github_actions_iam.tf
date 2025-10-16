locals {
  iam_role_name = "GitHubActionsReadonlyRole"
}

data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  count = var.deployment_name == "prod" ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates.0.sha1_fingerprint]
}

resource "aws_iam_role" "github_actions" {
  count = var.deployment_name == "prod" ? 1 : 0

  name        = local.iam_role_name
  description = "Managed by Terraform. IAM Role that a GitHub Actions runner can assume to authenticate with AWS."

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : aws_iam_openid_connect_provider.github_actions[0].arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringLike" : {
            "token.actions.githubusercontent.com:sub" : "repo:spack/spack-infrastructure:ref:refs/heads/main",
            "token.actions.githubusercontent.com:aud" : "sts.amazonaws.com"
          }
        }
      },
      {
        "Action" : "sts:AssumeRole",
        "Principal" : {
          # Unfortunately, we need to do this until https://github.com/hashicorp/terraform-provider-aws/issues/27034 is resolved.
          # This trust statement allows the role to assume itself, which is necessary for the GitHub Actions session user to run terraform plan.
          "AWS" : "arn:aws:sts::${data.aws_caller_identity.current.account_id}:assumed-role/GitHubActionsReadonlyRole/GitHubActions"
        },
        "Effect" : "Allow",
      },
    ]
  })
}

# The `ReadOnlyAccess` managed policy doesn't include secretsmanager, so we explicitly grant it here.
resource "aws_iam_role_policy" "github_actions" {
  count = var.deployment_name == "prod" ? 1 : 0

  name = "${local.iam_role_name}-policy"
  role = aws_iam_role.github_actions[0].id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "secretsmanager:GetSecretValue"
        ],
        "Resource" : "*"
      }
    ]
  })
}

# This policy grants the GitHub Actions role read-only access to most resources in the AWS account.
# There are some exceptions, such as secretsmanager (see inline_policy above)
resource "aws_iam_role_policy_attachment" "github_actions" {
  count = var.deployment_name == "prod" ? 1 : 0

  role       = aws_iam_role.github_actions[0].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}
