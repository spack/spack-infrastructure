# IAM Role for granting write access to spack-binaries bucket for the build cache pruner
resource "aws_iam_role" "full_crud_access_spack_binaries" {
  name        = "FullCRUDAccessToBucketSpackBinaries${local.suffix}"
  description = "Managed by Terraform. Grants Kubernetes pods access to read/write/delete objects from the spack-binaries S3 bucket"
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

resource "aws_iam_policy" "put_spack_binaries" {
  name        = "PutObjectsInBucketSpackBinaries${local.suffix}"
  description = "Managed by Terraform. Grant permission to PutObject for any object in the spack-binaries bucket"
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

resource "aws_iam_role_policy_attachment" "put_spack_binaries" {
  role       = aws_iam_role.full_crud_access_spack_binaries.name
  policy_arn = aws_iam_policy.put_spack_binaries.arn
}

resource "aws_iam_policy" "delete_spack_binaries" {
  name        = "DeleteObjectsFromBucketSpackBinaries${local.suffix}"
  description = "Managed by Terraform. Grant permission to DeleteObject for any object in the spack-binaries bucket"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:DeleteObject",
        "Resource" : "${module.protected_binary_mirror.bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_spack_binaries" {
  role       = aws_iam_role.full_crud_access_spack_binaries.name
  policy_arn = aws_iam_policy.delete_spack_binaries.arn
}

resource "kubectl_manifest" "build_cache_pruner_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: prune-buildcache
      namespace: custom
      annotations:
        # FullCRUDAccessToBucketSpackBinaries
        eks.amazonaws.com/role-arn: ${aws_iam_role.full_crud_access_spack_binaries.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.put_spack_binaries,
    aws_iam_role_policy_attachment.delete_spack_binaries
  ]
}
