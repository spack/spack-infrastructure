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
          "Action" : [
            "s3:PutObject",
            "s3:DeleteObject"
          ],
          "Resource" : "${module.protected_binary_mirror.bucket_arn}/develop/*"
        }
      ]
    }),
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : [
            "s3:PutObject",
            "s3:GetObject"
          ],
          "Resource" : "${module.pr_binary_mirror.logging_bucket_arn}/pruning/*"
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

module "spackbot_dev" {
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

  service_account_name      = "spackbotdev-spack-io"
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
        # The signing job needs to list the spec manifests it is about to sign,
        # and (via `spack gpg publish --update-index`) every spec manifest in the
        # stack mirror in order to rebuild the buildcache index.
        {
          "Effect" : "Allow",
          "Action" : "s3:ListBucket",
          "Resource" : module.protected_binary_mirror.bucket_arn
        },
        # The signing job syncs unsigned `*.spec.manifest.json` files down from
        # the stack mirror, re-signs them with the reputational key, syncs them
        # back up, then publishes the public key and regenerates the key and
        # buildcache indices (each a blob write plus a manifest write). Reads
        # cover the spec manifests and the blobs they point at; writes cover
        # `v3/manifests/{spec,key,index}/`, `blobs/`, and `v3/layout.json`.
        #
        # Signing only ever runs in protected-branch pipelines, whose mirrors
        # live at s3://spack-binaries/<ref>/<stack> for ref `develop` or
        # `releases/v*` -- so release tag prefixes (`v0.23.1/`), develop
        # snapshots (`develop-YYYY-MM-DD/`) and everything else in the bucket
        # stay out of reach. AbortMultipartUpload is only needed so that a
        # failed multipart upload of a large index can clean up after itself.
        {
          "Effect" : "Allow",
          "Action" : [
            "s3:GetObject",
            "s3:PutObject",
            "s3:AbortMultipartUpload"
          ],
          "Resource" : [
            "${module.protected_binary_mirror.bucket_arn}/develop/*",
            "${module.protected_binary_mirror.bucket_arn}/releases/*"
          ]
        }
      ]
    })
  ]

  service_account_name      = "notary"
  service_account_namespace = "pipeline"
}

module "rotate_keys" {
  source = "../iam_service_account"

  deployment_name  = var.deployment_name
  deployment_stage = var.deployment_stage

  service_account_iam_role_description = "IAM role used by the rotate-keys job to rotate the admin access keys."
  service_account_iam_policies = [
    jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : [
            "iam:GetGroup",
            "iam:ListAccessKeys",
            "iam:DeleteAccessKey"
          ],
          "Resource" : [
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:group/Custodians",
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/*"
          ]
        }
      ]
    })
  ]

  service_account_name      = "clear-admin-keys"
  service_account_namespace = "custom"
}

