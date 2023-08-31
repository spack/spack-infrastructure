locals {
  # For all non-production deployments, append the deployment name to all binary mirror resource names
  binary_mirror_name_suffix = var.deployment_name == "prod" ? "" : "-${var.deployment_name}"
}

module "pr_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_iam_username = "pull-requests-binary-mirror${local.binary_mirror_name_suffix}"
  bucket_name         = "spack-binaries-prs${local.binary_mirror_name_suffix}"

  enable_logging      = true
  logging_bucket_name = "spack-logs${local.binary_mirror_name_suffix}"
}

module "protected_binary_mirror" {
  source = "./modules/binary_mirror"

  bucket_iam_username = "protected-binary-mirror${local.binary_mirror_name_suffix}"
  bucket_name         = "spack-binaries${local.binary_mirror_name_suffix}"

  enable_logging = false
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
