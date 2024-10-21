locals {
  domain_suffix      = var.deployment_name == "prod" ? "" : "${var.deployment_name}."
  bucket_name_suffix = var.deployment_name == "prod" ? "" : "-${var.deployment_name}"
}

resource "aws_s3_bucket" "bootstrap" {
  bucket = "spack-bootstrap${local.bucket_name_suffix}"
}

resource "aws_s3_bucket_public_access_block" "bootstrap" {
  bucket = aws_s3_bucket.bootstrap.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "bootstrap" {
  bucket = aws_s3_bucket.bootstrap.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "PublicRead",
        "Effect" : "Allow",
        "Principal" : "*",
        "Action" : "s3:GetObject",
        "Resource" : "arn:aws:s3:::${aws_s3_bucket.bootstrap.bucket}/*"
      },
      {
        "Sid" : "StephenSachsPclusterWrite",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "arn:aws:iam::679174810898:root"
        },
        "Action" : [
          "s3:DeleteObject*",
          "s3:GetObject*",
          "s3:ListBucket*",
          "s3:PutObject*"
        ],
        "Resource" : "arn:aws:s3:::${aws_s3_bucket.bootstrap.bucket}/pcluster/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.bootstrap]
}

# ACM Certificates created for CloudFront distributions must be in us-east-1
# See https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html#https-requirements-certificate-issuer
provider "aws" {
  alias  = "acm"
  region = "us-east-1"
}

resource "aws_acm_certificate" "bootstrap" {
  domain_name       = "bootstrap.${local.domain_suffix}spack.io"
  validation_method = "DNS"

  provider = aws.acm
}

resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.bootstrap.domain_validation_options : dvo.domain_name => {
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

resource "aws_acm_certificate_validation" "bootstrap" {
  certificate_arn         = aws_acm_certificate.bootstrap.arn
  validation_record_fqdns = [for record in aws_route53_record.acm_validation : record.fqdn]

  provider = aws.acm
}

resource "aws_route53_record" "bootstrap" {
  zone_id = data.aws_route53_zone.spack_io.zone_id
  name    = "bootstrap.${local.domain_suffix}spack.io"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.bootstrap.domain_name
    zone_id                = aws_cloudfront_distribution.bootstrap.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_cloudfront_distribution" "bootstrap" {
  enabled = true

  aliases = ["bootstrap.${local.domain_suffix}spack.io"]

  is_ipv6_enabled = true

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.min_ttl_zero.id
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    target_origin_id       = aws_s3_bucket.bootstrap.bucket_regional_domain_name
    viewer_protocol_policy = "https-only"
  }

  origin {
    domain_name = aws_s3_bucket.bootstrap.bucket_regional_domain_name
    origin_id   = aws_s3_bucket.bootstrap.bucket_regional_domain_name
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.bootstrap.arn
    minimum_protocol_version = "TLSv1.2_2021"
    ssl_support_method       = "sni-only"
  }

  wait_for_deployment = true
}
