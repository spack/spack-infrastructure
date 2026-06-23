# The IAM role granting Spackbot full access to spack-binaries-prs S3 bucket.
resource "aws_iam_role" "full_crud_access_spack_binaries_prs" {
  name        = "FullCRUDAccessToBucketSpackBinariesPRs"
  description = "Managed by Terraform. Grants Kubernetes pods access to read/write/delete objects from the spack-binaries-prs S3 bucket"
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

resource "aws_iam_policy" "put_spack_binaries_prs" {
  name = "PutObjectsInBucketSpackBinariesPRs"
  description = "Managed by Terraform. Grant permission to PutObject for any object in the spack-binaries-prs bucket"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:PutObject",
        "Resource" : "arn:aws:s3:::spack-binaries-prs/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "put_spack_binaries_prs" {
  role       = aws_iam_role.full_crud_access_spack_binaries_prs.name
  policy_arn = aws_iam_policy.put_spack_binaries_prs.arn
}

resource "aws_iam_policy" "delete_spack_binaries_prs" {
  name = "DeleteObjectsFromBucketSpackBinariesPRs"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:DeleteObject",
        "Resource" : "arn:aws:s3:::spack-binaries-prs/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_spack_binaries_prs" {
  role       = aws_iam_role.full_crud_access_spack_binaries_prs.name
  policy_arn = aws_iam_policy.delete_spack_binaries_prs.arn
}

# spackbot-spack-io and spackbotdev-spack-io service accounts
resource "kubectl_manifest" "spackbot_service_account" {
  for_each  = toset(["spackbot", "spackbotdev"])
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${each.value}-spack-io
      namespace: spack
      annotations:
        # FullCRUDAccessToBucketSpackBinariesPRs
        eks.amazonaws.com/role-arn: ${aws_iam_role.full_crud_access_spack_binaries_prs.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.put_spack_binaries_prs,
    aws_iam_role_policy_attachment.delete_spack_binaries_prs
  ]
}
