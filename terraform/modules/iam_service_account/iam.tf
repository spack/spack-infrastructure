data "aws_eks_cluster" "this" {
  name = "spack${var.deployment_name != "prod" ? "-${var.deployment_name}" : ""}-${var.deployment_stage}"
}

data "aws_iam_openid_connect_provider" "this" {
  url = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_role" "this" {
  name        = "${var.service_account_name}-role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. ${var.service_account_iam_role_description}"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : data.aws_iam_openid_connect_provider.this.arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${data.aws_iam_openid_connect_provider.this.url}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "this" {
  for_each = toset(var.service_account_iam_policies)
  name     = "${var.service_account_name}-policy-${var.deployment_name}-${var.deployment_stage}${index(var.service_account_iam_policies, each.value)}"
  policy   = each.value
}

resource "aws_iam_role_policy_attachment" "this" {
  for_each   = aws_iam_policy.this
  role       = aws_iam_role.this.name
  policy_arn = each.value.arn
}
