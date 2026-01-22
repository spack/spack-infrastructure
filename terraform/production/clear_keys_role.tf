resource "aws_iam_role" "clear_keys" {
  name        = "ClearAdministratorsIAMAccessKeys"
  description = "Delete IAM access keys for users in the Administrators group"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.production_cluster.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.production_cluster.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "clear_keys" {
  name        = "ClearAdministratorsIAMAccessKeys"
  description = "This policy is used by a Kubernetes cron job. It allows us to delete IAM Access keys for users in the Administrators group."
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "iam:DeleteAccessKey",
          "iam:GetGroup",
          "iam:ListAccessKeys"
        ],
        "Resource" : [
          "arn:aws:iam::588562868276:user/*",
          "arn:aws:iam::588562868276:group/Administrators"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "clear_keys" {
  role       = aws_iam_role.clear_keys.name
  policy_arn = aws_iam_policy.clear_keys.arn
}

resource "kubectl_manifest" "clear_keys_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: clear-admin-keys
      namespace: custom
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.clear_keys.arn}
  YAML
  depends_on = [
    aws_iam_role_policy.clear_keys
  ]
}
