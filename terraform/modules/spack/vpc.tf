module "vpc" {
  # https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "spack-${var.deployment_name}"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  public_subnets  = var.public_subnets
  private_subnets = var.private_subnets

  enable_nat_gateway      = true
  single_nat_gateway      = false
  enable_dns_hostnames    = true
  one_nat_gateway_per_az  = true
  map_public_ip_on_launch = true

  # Don't create a DB subnet group here, instead
  # we create it explicitly below so that we can
  # configure its subnets directly.
  create_database_subnet_group = false

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

# S3 Gateway Endpoint to allow cheaper traffic between our
# public/private subnets and S3.
# https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html
resource "aws_vpc_endpoint" "s3_gateway" {
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  vpc_id            = module.vpc.vpc_id
  route_table_ids   = concat(module.vpc.private_route_table_ids, module.vpc.public_route_table_ids)
}
