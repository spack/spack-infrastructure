data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}
