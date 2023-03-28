data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}

resource "aws_route53_record" "opensearch" {
  name    = "opensearch.spack.io"
  records = [aws_opensearch_domain.spack.endpoint]
  ttl     = 300
  type    = "CNAME"
  zone_id = data.aws_route53_zone.spack_io.zone_id
}
