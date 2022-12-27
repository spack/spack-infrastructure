module "vpc" {
  # https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.18.1"

  name = local.cluster_name
  cidr = local.vpc_cidr

  azs = local.azs
  private_subnets = [
    "192.168.128.0/19",
    "192.168.160.0/19",
    "192.168.192.0/19",
    "192.168.224.0/19",
  ]
  public_subnets = [
    "192.168.0.0/19",
    "192.168.32.0/19",
    "192.168.64.0/19",
    "192.168.96.0/19"
  ]

  enable_nat_gateway   = true
  single_nat_gateway   = false
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
    "karpenter.sh/discovery" = "true"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
    "karpenter.sh/discovery"          = "true"
  }
}
