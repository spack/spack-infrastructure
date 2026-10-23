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

  # Referencing the bucket through its policy makes log delivery wait until
  # the bucket allows it.
  logging_bucket_name      = aws_s3_bucket_policy.logs.bucket
  enable_s3_access_logging = true

  cdn_domain      = "binaries-prs.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}

module "protected_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_name = "spack-binaries${local.bucket_name_suffix}"

  # Referencing the bucket through its policy makes log delivery wait until
  # the bucket allows it.
  logging_bucket_name       = aws_s3_bucket_policy.logs.bucket
  enable_s3_access_logging  = false
  enable_cloudfront_logging = var.deployment_name == "prod"

  cdn_domain      = "binaries.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cache_policy_id = aws_cloudfront_cache_policy.min_ttl_zero.id
}
