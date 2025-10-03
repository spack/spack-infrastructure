# IAM Role for granting delete access to spack-binaries bucket for the snapshot pruner
resource "aws_iam_role" "delete_spack_binaries" {
  name        = "DeleteFromBucketSpackBinaries${local.suffix}"
  description = "Managed by Terraform. Grants Kubernetes pods access to delete objects from the spack-binaries S3 bucket"
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

resource "aws_iam_policy" "delete_spack_binaries" {
  name        = "DeleteObjectsFromBucketSpackBinaries${local.suffix}"
  description = "Allows deletion of any object in the ${module.protected_binary_mirror.bucket_name} bucket."
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
  role       = aws_iam_role.delete_spack_binaries.name
  policy_arn = aws_iam_policy.delete_spack_binaries.arn
}

resource "kubectl_manifest" "snapshot_pruner_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: prune-snapshots
      namespace: custom
      annotations:
        # DeleteFromBucketSpackBinaries
        eks.amazonaws.com/role-arn: ${aws_iam_role.delete_spack_binaries.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.delete_spack_binaries
  ]
}
