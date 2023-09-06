locals {
  suffix = var.deployment_name == "prod" ? "" : "-${var.deployment_name}"
}

# IAM Role for granting read access to spack-binaries and write access to the cache index
data "aws_iam_policy_document" "cache_indexer_assume_role_policy" {
  statement {
    sid     = ""
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
  }
}

resource "aws_iam_role" "cache_indexer" {
  name               = "CacheIndexer${local.suffix}"
  assume_role_policy = data.aws_iam_policy_document.cache_indexer_assume_role_policy.json
}

data "aws_iam_policy_document" "cache_indexer_policy" {
  statement {
    sid     = ""
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = [
      "${module.protected_binary_mirror.bucket_arn}/*",
    ]
  }

  statement {
    sid     = ""
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:DeleteObject"]

    resources = [
      "${module.protected_binary_mirror.bucket_arn}/cache_spack_io_index.json",
    ]
  }
}

resource "aws_iam_role_policy" "cache_indexer_policy" {
  name   = "CacheIndexerPolicy${local.suffix}"
  role   = aws_iam_role.cache_indexer.id
  policy = data.aws_iam_policy_document.cache_indexer_policy.json
}

resource "kubectl_manifest" "cache_indexer_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: index-binary-caches
      namespace: custom
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.cache_indexer.arn}
  YAML
  depends_on = [
    aws_iam_role_policy.cache_indexer_policy
  ]
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
