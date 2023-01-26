module "vpc" {
  # https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.18.1"

  name = local.cluster_name
  cidr = local.vpc_cidr

  azs = local.azs
  public_subnets = [
    "10.0.0.0/19",
    "10.0.32.0/19",
  ]
  private_subnets = [
    "10.0.64.0/19",
    "10.0.96.0/19",
    "10.0.128.0/19",
    "10.0.160.0/19",
  ]
  database_subnets = [
    "10.0.192.0/19",
    "10.0.224.0/19",
  ]

  # Create a DB subnet group for RDS (see rds.tf)
  create_database_subnet_group = true

  enable_nat_gateway   = true
  single_nat_gateway   = terraform.workspace != "production"
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
