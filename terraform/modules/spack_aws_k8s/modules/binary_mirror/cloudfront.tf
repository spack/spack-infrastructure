data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}

resource "aws_acm_certificate" "binary_mirror" {
  domain_name       = var.cdn_domain
  validation_method = "DNS"

  # ACM Certificates created for CloudFront distributions must be in us-east-1
  # See https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html#https-requirements-certificate-issuer
  region = "us-east-1"
}

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.binary_mirror.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  name    = each.value.name
  records = [each.value.record]
  ttl     = 300
  type    = each.value.type
  zone_id = data.aws_route53_zone.spack_io.zone_id
}

resource "aws_acm_certificate_validation" "binary_mirror" {
  certificate_arn         = aws_acm_certificate.binary_mirror.arn
  validation_record_fqdns = [for record in aws_route53_record.acm_validation : record.fqdn]

  # ACM Certificates created for CloudFront distributions must be in us-east-1
  # See https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html#https-requirements-certificate-issuer
  region = "us-east-1"
}

resource "aws_route53_record" "binary_mirror" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = var.cdn_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.binary_mirror.domain_name
    zone_id                = aws_cloudfront_distribution.binary_mirror.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_cloudfront_distribution" "binary_mirror" {
  enabled = true

  aliases = [var.cdn_domain]

  is_ipv6_enabled = true

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cache_policy_id        = var.cache_policy_id
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    target_origin_id       = aws_s3_bucket.binary_mirror.bucket_regional_domain_name
    viewer_protocol_policy = "https-only"
  }

  origin {
    domain_name = aws_s3_bucket.binary_mirror.bucket_regional_domain_name
    origin_id   = aws_s3_bucket.binary_mirror.bucket_regional_domain_name
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.binary_mirror.arn
    minimum_protocol_version = "TLSv1.2_2021"
    ssl_support_method       = "sni-only"
  }

  wait_for_deployment = true
}

# CloudFront standard logging (v2), delivered to S3 via CloudWatch vended logs.
# Log delivery for CloudFront distributions must be configured in us-east-1,
# regardless of where the destination bucket lives.
resource "aws_cloudwatch_log_delivery_source" "cloudfront" {
  count = var.enable_cloudfront_logging ? 1 : 0

  region       = "us-east-1"
  name         = "${var.bucket_name}-cloudfront"
  log_type     = "ACCESS_LOGS"
  resource_arn = aws_cloudfront_distribution.binary_mirror.arn
}

resource "aws_cloudwatch_log_delivery_destination" "cloudfront" {
  count = var.enable_cloudfront_logging ? 1 : 0

  region        = "us-east-1"
  name          = "${var.bucket_name}-cloudfront-s3"
  output_format = "json"

  delivery_destination_configuration {
    destination_resource_arn = "arn:aws:s3:::${var.logging_bucket_name}/cloudfront"
  }
}

resource "aws_cloudwatch_log_delivery" "cloudfront" {
  count = var.enable_cloudfront_logging ? 1 : 0

  region                   = "us-east-1"
  delivery_source_name     = aws_cloudwatch_log_delivery_source.cloudfront[0].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.cloudfront[0].arn

  # Only the fields needed for traffic analysis; cookies, query strings and
  # referrers are left out on purpose. asn and c-country are v2-only fields.
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
