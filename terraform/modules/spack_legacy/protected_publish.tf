# IAM Role for granting write access to spack-binaries bucket for protected-publish
resource "aws_iam_role" "write_access_spack_binaries" {
  name        = "WriteAccessToBucketSpackBinaries${local.suffix}"
  description = "Managed by Terraform. Grants Kubernetes pods access to write objects to the spack-binaries S3 bucket"
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
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "write_spack_binaries" {
  name        = "WriteBucketSpackBinaries${local.suffix}"
  description = "Allows writing any objects to the ${module.protected_binary_mirror.bucket_name} bucket"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:PutObject",
        "Resource" : "${module.protected_binary_mirror.bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "write_spack_binaries" {
  role       = aws_iam_role.write_access_spack_binaries.name
  policy_arn = aws_iam_policy.write_spack_binaries.arn
}

resource "kubectl_manifest" "protected_publish_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: protected-publish
      namespace: custom
      annotations:
        # WriteAccessToBucketSpackBinaries
        eks.amazonaws.com/role-arn: ${aws_iam_role.write_access_spack_binaries.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.write_spack_binaries,
  ]
}
