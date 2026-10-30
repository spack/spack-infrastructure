# CloudFront access logs for mirror.spack.io, the source tarball mirror backed
# by s3://spack-llnl-mirror. The distribution itself isn't managed by this
# repo; only its log delivery is. Logs land next to the binary mirrors' in
# s3://spack-logs/cloudfront/<distribution-id>/, which the logs bucket's
# policy and 90-day lifecycle rule already cover.
locals {
  source_mirror_distribution_id = "EO0PKEEBAGSI0"
}

data "aws_cloudfront_distribution" "source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  id = local.source_mirror_distribution_id

  lifecycle {
    postcondition {
      condition     = contains(self.aliases, "mirror.spack.io")
      error_message = "Distribution ${local.source_mirror_distribution_id} is no longer mirror.spack.io."
    }
  }
}

# Log delivery for CloudFront distributions must be configured in us-east-1,
# regardless of where the destination bucket lives.
resource "aws_cloudwatch_log_delivery_source" "source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  region       = "us-east-1"
  name         = "spack-llnl-mirror-cloudfront"
  log_type     = "ACCESS_LOGS"
  resource_arn = data.aws_cloudfront_distribution.source_mirror[0].arn
}

resource "aws_cloudwatch_log_delivery_destination" "source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  region        = "us-east-1"
  name          = "spack-llnl-mirror-cloudfront-s3"
  output_format = "json"

  delivery_destination_configuration {
    # Referencing the bucket through its policy makes log delivery wait until
    # the bucket allows it.
    destination_resource_arn = "arn:aws:s3:::${aws_s3_bucket_policy.logs.bucket}/cloudfront"
  }
}

resource "aws_cloudwatch_log_delivery" "source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  region                   = "us-east-1"
  delivery_source_name     = aws_cloudwatch_log_delivery_source.source_mirror[0].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.source_mirror[0].arn

  # Same fields as the binary mirrors' logs, so the same analysis applies.
  record_fields = [
    "date",
    "time",
    "x-edge-location",
    "c-ip",
    "asn",
    "c-country",
    "cs-method",
    "cs-uri-stem",
    "sc-status",
    "sc-bytes",
    "time-taken",
    "cs(User-Agent)",
    "x-edge-result-type",
    "sc-range-start",
    "sc-range-end",
  ]

  s3_delivery_configuration {
    suffix_path = "{DistributionId}/{yyyy}/{MM}/{dd}"
  }
}
