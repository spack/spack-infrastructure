module "db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.2.3"

  identifier = "gitlab-${terraform.workspace}"

  engine               = "postgres"
  engine_version       = "14"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = "db.t3.xlarge"

  db_name  = "gitlabhq_production"
  username = "postgres"
  port     = "5432"

  publicly_accessible  = false
  db_subnet_group_name = module.vpc.database_subnet_group

  maintenance_window              = "Sun:00:00-Sun:03:00"
  backup_window                   = "03:00-06:00"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  create_cloudwatch_log_group     = true

  backup_retention_period = 7
  skip_final_snapshot     = true
  deletion_protection     = false

  allocated_storage     = 500
  max_allocated_storage = 1000

  vpc_security_group_ids = [module.security_group.security_group_id]
}

module "security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "4.16.2"

  name        = "postgres_sg"
  description = "Security group for RDS PostgreSQL database"
  vpc_id      = module.vpc.vpc_id

  ingress_with_cidr_blocks = [
    {
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      description = "PostgreSQL access from within VPC"
      cidr_blocks = module.vpc.vpc_cidr_block
    },
  ]
}
