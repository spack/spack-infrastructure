# Develop build cache (protected mirror)
module "develop_mirror" {
  source = "./modules/spack-binary-mirror"

  # Don't add a suffix for the production mirror. It was created before
  # this Terraform module, so we must make an exception here.
  resource_suffix = var.deployment_name != "production" ? "-${var.deployment_name}" : ""
}

# Serve static index.html from the develop mirror bucket
resource "aws_s3_bucket_website_configuration" "spack_develop_mirror" {
  bucket = module.develop_mirror.s3_bucket.id

  index_document {
    suffix = "index.html"
  }
}



# PR build cache(public mirror)
module "pr_mirror" {
  source = "./modules/spack-binary-mirror"

  # Don't add a suffix for the production mirror. It was created before
  # this Terraform module, so we must make an exception here.
  resource_suffix = var.deployment_name != "production" ? "-${var.deployment_name}" : ""
}

# Delete objects older than 14 days for the PR build cache only
resource "aws_s3_bucket_lifecycle_configuration" "spack_binary_mirror" {
  bucket = module.pr_mirror.s3_bucket.id
  rule {
    id = "DeleteOldObjects"

    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 0
    }

    expiration {
      days                         = 14
      expired_object_delete_marker = false
    }
  }
}
