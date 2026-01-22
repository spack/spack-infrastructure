resource "aws_iam_role" "rotate_keys" {
  name        = "RotateIAMAccessKeysForGitLab"
  description = "Rotate IAM access keys used by GitLab to write to S3 buckets for our Spack binary mirrors"
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

resource "aws_iam_policy" "rotate_keys" {
  name        = "RotateIAMAccessKeysForGitLab"
  description = "This policy is used by a Kubernetes cron job. It allows us to rotate the IAM Access keys used by GitLab to write to S3 buckets for our binary mirrors."
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "iam:DeleteAccessKey",
          "iam:CreateAccessKey",
          "iam:ListAccessKeys"
        ],
        "Resource" : [
          "arn:aws:iam::588562868276:user/develop-binary-mirror",
          "arn:aws:iam::588562868276:user/pull-requests-binary-mirror",
          "arn:aws:iam::588562868276:user/test-key-rotation",
          "arn:aws:iam::588562868276:user/protected-binary-mirror",
          "arn:aws:iam::588562868276:user/cray-binary-mirror"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rotate_keys" {
  role       = aws_iam_role.rotate_keys.name
  policy_arn = aws_iam_policy.rotate_keys.arn
}

resource "kubectl_manifest" "rotate_keys_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: rotate-keys
      namespace: custom
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.rotate_keys.arn}
  YAML
  depends_on = [
    aws_iam_role_policy.rotate_keys
  ]
}
