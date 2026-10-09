# This is a cache policy that gets used by both binary mirror CDNs.
resource "aws_cloudfront_cache_policy" "min_ttl_zero" {
  name        = "CachingAllowNoCache${local.suffix}"
  comment     = "Same as Managed - Caching Optimized, but min TTL=0"
  default_ttl = 86400
  max_ttl     = 31536000
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }

    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
  }
}

module "pr_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_name = "spack-binaries-prs${local.bucket_name_suffix}"

  enable_logging      = true
  logging_bucket_name = "spack-logs${local.bucket_name_suffix}"

  cdn_domain      = "binaries-prs.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}

module "protected_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_name = "spack-binaries${local.bucket_name_suffix}"

  enable_logging = false

  cdn_domain      = "binaries.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}


# Permissions on the mirror buckets live here, next to the buckets themselves.
# The IAM groups/roles that consume them are declared in the root module and
# reference these via the binary_cache_*_policy_arn outputs.
#
# Read-only access is split per bucket so that the groups can compose it:
# observers get the protected mirror only, maintainers get both.

resource "aws_iam_policy" "protected_binary_cache_read_only" {
  name = "ProtectedBinaryCacheReadOnly${local.suffix}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Bucket-level actions authorize against the bucket ARN, not the object ARN.
        Sid    = "ListProtectedBinaryMirror"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:ListBucketVersions",
          "s3:ListBucketMultipartUploads",
          "s3:GetBucketLocation",
        ]
        Resource = [
          module.protected_binary_mirror.bucket_arn,
        ]
      },
      {
        Sid    = "ReadProtectedBinaryMirrorObjects"
        Effect = "Allow"
        Action = [
          "s3:Get*",
          "s3:List*",
        ]
        Resource = [
          "${module.protected_binary_mirror.bucket_arn}/*",
        ]
      },
    ]
  })
}

resource "aws_iam_policy" "pr_binary_cache_read_only" {
  name = "PRBinaryCacheReadOnly${local.suffix}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListPRBinaryMirror"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:ListBucketVersions",
          "s3:ListBucketMultipartUploads",
          "s3:GetBucketLocation",
        ]
        Resource = [
          module.pr_binary_mirror.bucket_arn,
        ]
      },
      {
        Sid    = "ReadPRBinaryMirrorObjects"
        Effect = "Allow"
        Action = [
          "s3:Get*",
          "s3:List*",
        ]
        Resource = [
          "${module.pr_binary_mirror.bucket_arn}/*",
        ]
      },
    ]
  })
}

resource "aws_iam_policy" "binary_cache_full_access" {
  name = "BinaryCacheFullAccess${local.suffix}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Deliberately not s3:* on the bucket ARN, which would also grant
        # DeleteBucket and PutBucketPolicy on the mirrors.
        Sid    = "ListBinaryMirrors"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:ListBucketVersions",
          "s3:ListBucketMultipartUploads",
          "s3:GetBucketLocation",
        ]
        Resource = [
          module.protected_binary_mirror.bucket_arn,
          module.pr_binary_mirror.bucket_arn,
        ]
      },
      {
        Sid    = "AllBinaryMirrorObjectActions"
        Effect = "Allow"
        Action = [
          "s3:*Object*",
          "s3:AbortMultipartUpload",
          "s3:RestoreObject",
        ]
        Resource = [
          "${module.protected_binary_mirror.bucket_arn}/*",
          "${module.pr_binary_mirror.bucket_arn}/*",
        ]
      },
    ]
  })
}
