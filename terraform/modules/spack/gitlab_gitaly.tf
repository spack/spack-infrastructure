module "gitaly_cluster" {
  source = "./modules/gitaly_cluster"

  deployment_name = var.deployment_name
  vpc_id          = module.vpc.vpc_id
  vpc_cidr        = module.vpc.vpc_cidr_block
  db_subnet_ids   = module.vpc.private_subnets
}
