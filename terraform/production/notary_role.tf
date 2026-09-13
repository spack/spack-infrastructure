# The IAM role to enable signing runners
resource "aws_iam_role" "notary" {
  name = "NotaryRole"
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

# The policy to allow for KMS key decryption and S3 Access
resource "aws_iam_role_policy" "notary" {
  name = "NotaryPolicy"
  role = aws_iam_role.notary.id
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      # Reputational Encryption Key
      {
        "Effect" : "Allow",
        "Action" : [
          "kms:GetPublicKey",
          "kms:Decrypt",
          "kms:DescribeKey"
        ],
        "Resource" : "arn:aws:kms:us-east-1:588562868276:key/bc739d17-8569-4741-9385-9264715b90b6"
      },
      # Test Key
      {
        "Effect" : "Allow",
        "Action" : [
          "kms:GetPublicKey",
          "kms:Decrypt",
          "kms:DescribeKey"
        ],
        "Resource" : "arn:aws:kms:us-east-1:588562868276:key/e811e4c5-ea63-4da3-87d4-664dc5395169"
      },
      # S3 Full Access
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:*",
          "s3-object-lambda:*"
        ],
        "Resource" : "*"
      }
    ]
  })
}

# The ServiceAccount to be used by the signing runner
resource "kubectl_manifest" "notary_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: notary
      namespace: pipeline
      annotations:
        # NotaryRole
        eks.amazonaws.com/role-arn: ${aws_iam_role.notary.arn}
  YAML
  depends_on = [
    aws_iam_role_policy.notary
  ]
}
