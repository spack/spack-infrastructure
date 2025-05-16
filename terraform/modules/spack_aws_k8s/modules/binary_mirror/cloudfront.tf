data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}

# ACM Certificates created for CloudFront distributions must be in us-east-1
# See https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html#https-requirements-certificate-issuer
provider "aws" {
  alias  = "acm"
  region = "us-east-1"

  assume_role {
    role_arn = "arn:aws:iam::588562868276:role/terraform-role"
  }
}

resource "aws_acm_certificate" "binary_mirror" {
  domain_name       = var.cdn_domain
  validation_method = "DNS"

  provider = aws.acm
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

  provider = aws.acm
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
