module "vpc" {
  # https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.18.1"

  name = "spack-${var.deployment_name}"
  cidr = var.vpc_cidr

  azs = var.availability_zones
  public_subnets = var.public_subnets
  private_subnets = var.private_subnets
  database_subnets = var.database_subnets

  # Create a DB subnet group for RDS (see rds.tf)
  create_database_subnet_group = true

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
