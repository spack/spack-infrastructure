module "build_cache_pruner" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:PutObject",
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/*"
        }
      ]
    }),
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:DeleteObject",
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/*"
        }
      ]
    })
  ]
  service_account_name      = "prune-buildcache"
  service_account_namespace = "custom"
}

module "cache_indexer" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:GetObject",
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/*",
        },
        {
          "Effect" : "Allow",
          "Action" : ["s3:PutObject", "s3:DeleteObject"],
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/cache_spack_io_index.json",
        }
      ]
    })
  ]
  service_account_name      = "index-binary-caches"
  service_account_namespace = "custom"
}
resource "kubectl_manifest" "cache_indexer_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: cache-indexer-config
      namespace: custom
    data:
      bucket_name: ${module.protected_binary_mirror.bucket_name}
  YAML
}


module "protected_publish" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:PutObject",
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/*"
        }
      ]
    })
  ]

  service_account_name      = "protected-publish"
  service_account_namespace = "custom"
}

module "spackbot" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:PutObject",
          "Resource" : "${module.pr_binary_mirror.bucket_arn}/*"
        }
      ]
    }),
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : "s3:DeleteObject",
          "Resource" : "${module.pr_binary_mirror.bucket_arn}/*"
        }
      ]
    })
  ]

  service_account_name      = "spackbot-spack-io"
  service_account_namespace = "spack"
}

module "fluent_bit" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Action" : [
            "es:ESHttp*"
          ],
          "Resource" : aws_opensearch_domain.spack.arn,
          "Effect" : "Allow"
        }
      ]
    })
  ]

  service_account_name      = "fluent-bit"
  service_account_namespace = "fluent-bit"
}

module "notary" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_policies = [
    jsonencode({
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
  ]

  service_account_name      = "notary"
  service_account_namespace = "pipeline"
}
