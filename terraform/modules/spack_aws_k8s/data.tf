data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}

data "aws_ec2_managed_prefix_list" "cluster_prefix_list" {
  name = "com.amazonaws.${var.region}.vpc-lattice"
}
data "aws_ec2_managed_prefix_list" "cluster_prefix_list_ipv6" {
  name = "com.amazonaws.${var.region}.ipv6.vpc-lattice"
}
