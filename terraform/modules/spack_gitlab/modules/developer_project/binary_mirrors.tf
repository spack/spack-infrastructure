locals {
  bucket_name_suffix = "-${replace(data.gitlab_project.this.path_with_namespace, "/", "-")}${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}-${var.deployment_stage}"
}

data "aws_cloudfront_cache_policy" "min_ttl_zero" {
  # Same cache policy that is used for production buckets
  name = "CachingAllowNoCache${"${var.deployment_name != "prod" ? "-${var.deployment_name}" : ""}-${var.deployment_stage}"}"
}

module "pr_binary_mirror" {
  source = "../../../binary_mirror"

  bucket_iam_username = "pull-requests-binary-mirror${local.bucket_name_suffix}"
  bucket_name         = "spack-binaries-prs${local.bucket_name_suffix}"

  enable_logging      = true
  logging_bucket_name = "spack-logs${local.bucket_name_suffix}"

  cdn_domain      = "binaries-prs${local.bucket_name_suffix}.spack.io"
  cache_policy_id = data.aws_cloudfront_cache_policy.min_ttl_zero.id
}

module "protected_binary_mirror" {
  source = "../../../binary_mirror"

  bucket_iam_username = "protected-binary-mirror${local.bucket_name_suffix}"
  bucket_name         = "spack-binaries${local.bucket_name_suffix}"

  enable_logging = false

  cdn_domain      = "binaries${local.bucket_name_suffix}.spack.io"
  cache_policy_id = data.aws_cloudfront_cache_policy.min_ttl_zero.id
}
