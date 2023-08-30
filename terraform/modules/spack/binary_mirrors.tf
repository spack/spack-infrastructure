module "pr_binary_mirror" {
  source = "./modules/binary_mirror"

  public              = var.public_binary_mirrors
  bucket_iam_username = "pull-requests-binary-mirror${var.binary_mirror_bucket_suffix}"
  bucket_name         = "spack-binaries-prs${var.binary_mirror_bucket_suffix}"

  enable_logging      = true
  logging_bucket_name = "spack-logs${var.binary_mirror_bucket_suffix}"
}

module "protected_binary_mirror" {
  source = "./modules/binary_mirror"

  public              = var.public_binary_mirrors
  bucket_iam_username = "protected-binary-mirror${var.binary_mirror_bucket_suffix}"
  bucket_name         = "spack-binaries${var.binary_mirror_bucket_suffix}"

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
