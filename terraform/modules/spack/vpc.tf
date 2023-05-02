module "vpc" {
  # https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.18.1"

  name = "spack-${var.deployment_name}"
  cidr = var.vpc_cidr

  azs              = var.availability_zones
  public_subnets   = var.public_subnets
  private_subnets  = var.private_subnets

  enable_nat_gateway   = true
  single_nat_gateway   = false
  enable_dns_hostnames = true
  one_nat_gateway_per_az = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
    # This tag *must* match the Karpenter subnetSelector in order for
    # Karpenter to be able to provision nodes on this subnet.
    # (See karpenter.tf for that value)
    "karpenter.sh/discovery" = var.deployment_name
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
    # This tag *must* match the Karpenter subnetSelector in order for
    # Karpenter to be able to provision nodes on this subnet.
    # (See karpenter.tf for that value)
    "karpenter.sh/discovery" = var.deployment_name
  }
}

resource "aws_db_subnet_group" "spack" {
  name       = "spack-db-subnet-group-${var.deployment_name}"
  subnet_ids = module.vpc.private_subnets
}
