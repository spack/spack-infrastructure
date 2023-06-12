# Retrieve the master password for the gitlab production database,
# since it has been changed since terraform created the RDS instance
data "aws_secretsmanager_secret" "gitlab_db_credentials" {
  arn = var.gitlab_db_master_credentials_secret
}
data "aws_secretsmanager_secret_version" "gitlab_db_credentials" {
  secret_id = data.aws_secretsmanager_secret.gitlab_db_credentials.id
}

# Compute local values required in the gitlab_db module
locals {
  gitlab_db_master_password = jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_credentials.secret_string)["password"]
}

module "gitlab_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.2.3"

  identifier = "gitlab-${var.deployment_name}"

  engine               = "postgres"
  engine_version       = "14.3"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name                = "gitlabhq_production"
  username               = "postgres"
  port                   = "5432"
  create_random_password = false
  password               = local.gitlab_db_master_password

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.spack.name

  maintenance_window              = "Sun:00:00-Sun:03:00"
  backup_window                   = "03:00-06:00"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  create_cloudwatch_log_group     = true

  backup_retention_period = 7
  skip_final_snapshot     = false
  deletion_protection     = true

  allocated_storage     = 500
  max_allocated_storage = 1000

  vpc_security_group_ids = [module.postgres_security_group.security_group_id]
}

module "postgres_security_group" {
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
