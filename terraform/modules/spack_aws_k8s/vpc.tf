locals {
  azs      = slice(data.aws_availability_zones.available.names, 0, min(4, length(data.aws_availability_zones.available.names)))
  vpc_cidr = "10.0.0.0/16"
}

data "aws_availability_zones" "available" {
  # Do not include local zones
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.16.0"

  name = "spack${local.suffix}"
  cidr = local.vpc_cidr

  azs             = local.azs
  private_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 3, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 3, k + 4)]

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
    # Tags subnets for Karpenter auto-discovery
    "karpenter.sh/discovery" = local.eks_cluster_name
  }
}

# S3 Gateway Endpoint to allow cheaper traffic between our
# public/private subnets and S3.
# https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html
resource "aws_vpc_endpoint" "s3_gateway" {
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  vpc_id            = module.vpc.vpc_id
  route_table_ids   = concat(module.vpc.private_route_table_ids, module.vpc.public_route_table_ids)
}
