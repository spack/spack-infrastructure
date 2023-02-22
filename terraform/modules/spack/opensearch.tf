resource "aws_iam_role" "fluent_bit_role" {
  name        = "FluentBitRole-${var.deployment_name}"
  description = "IAM role that, when associated with a k8s service account, allows a fluent-bit pod to post logs to OpenSearch."

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:fluent-bit:fluent-bit",
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "fluent_bit_policy" {
  name = "FluentBitPolicy-${var.deployment_name}"
  role = aws_iam_role.fluent_bit_role.id
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Action" : [
          "es:ESHttp*"
        ],
        "Resource" : "arn:aws:es:us-east-1:588562868276:domain/spack",
        "Effect" : "Allow"
      }
    ]
  })
}

# TODO: encode OpenSearch domain/cluster here too
