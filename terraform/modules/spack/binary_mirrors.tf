locals {
  # For all non-production deployments, append the deployment name to all binary mirror resource names
  binary_mirror_name_suffix = var.deployment_name == "prod" ? "" : "-${var.deployment_name}"
}

# This is a cache policy that gets used by both binary mirror CDNs.
resource "aws_cloudfront_cache_policy" "min_ttl_zero" {
  name        = "CachingAllowNoCache${local.binary_mirror_name_suffix}"
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

  bucket_iam_username = "pull-requests-binary-mirror${local.binary_mirror_name_suffix}"
  bucket_name         = "spack-binaries-prs${local.binary_mirror_name_suffix}"

  enable_logging      = true
  logging_bucket_name = "spack-logs${local.binary_mirror_name_suffix}"

  cdn_domain      = "binaries-prs.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}

module "protected_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_iam_username = "protected-binary-mirror${local.binary_mirror_name_suffix}"
  bucket_name         = "spack-binaries${local.binary_mirror_name_suffix}"

  enable_logging = false

  cdn_domain      = "binaries.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}

resource "aws_s3_bucket_lifecycle_configuration" "pr_binary_mirror" {
  bucket = module.pr_binary_mirror.bucket_name

  rule {
    id = "DeleteOldObjects"

    expiration {
      days = 14
    }

    status = "Disabled"
  }
}
