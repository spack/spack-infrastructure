resource "aws_s3_bucket" "spack_gantry" {
  bucket = "spack-gantry${local.suffix}"
}

resource "aws_iam_role" "spack_gantry" {
  name        = "SpackGantryRole${local.suffix}"
  description = "Managed by Terraform. Grants Kubernetes pods access to read/write/delete objects from the ${aws_s3_bucket.spack_gantry.id} S3 bucket."
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

resource "aws_iam_policy" "spack_gantry" {
  name        = "SpackGantryPolicy${local.suffix}"
  description = "Managed by Terraform. Allows writing any objects to the ${aws_s3_bucket.spack_gantry.id} bucket."
  # Policy taken from https://litestream.io/guides/s3/#restrictive-iam-policy
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ],
        "Resource" : aws_s3_bucket.spack_gantry.arn
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetObject"
        ],
        "Resource" : [
          aws_s3_bucket.spack_gantry.arn,
          "${aws_s3_bucket.spack_gantry.arn}/*",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "spack_gantry" {
  role       = aws_iam_role.spack_gantry.name
  policy_arn = aws_iam_policy.spack_gantry.arn
}

resource "kubectl_manifest" "spack_gantry_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: spack-gantry
      namespace: spack
      annotations:
        # SpackGantryRole
        eks.amazonaws.com/role-arn: ${aws_iam_role.spack_gantry.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.spack_gantry,
  ]
}

resource "kubectl_manifest" "spack_gantry_config" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: spack-gantry-config
      namespace: spack
    data:
      litestream-config.yaml: |-
        dbs:
          - path: /var/lib/gantry/db
            replicas:
              - type: s3
                bucket: ${aws_s3_bucket.spack_gantry.id}
                path: db
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.spack_gantry,
  ]
}
