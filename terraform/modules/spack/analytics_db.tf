data "aws_secretsmanager_secret" "analytics_db_credentials" {
  arn = var.analytics_db_credentials_secret
}
data "aws_secretsmanager_secret_version" "analytics_db_credentials" {
  secret_id = data.aws_secretsmanager_secret.analytics_db_credentials.id
}
locals {
  analytics_db_master_password = jsondecode(data.aws_secretsmanager_secret_version.analytics_db_credentials.secret_string)["password"]
}

module "analytics_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.9.0"

  identifier = "analytics-${var.deployment_name}"

  engine               = "postgres"
  family               = "postgres15"
  major_engine_version = "15"
  engine_version       = "15.5"
  instance_class       = var.gitlab_db_instance_class

  # Credentials
  db_name                = "analytics"
  username               = "postgres"
  port                   = "5432"
  create_random_password = false
  password               = local.analytics_db_master_password

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.spack.name

  maintenance_window              = "Sun:00:00-Sun:03:00"
  backup_window                   = "03:00-06:00"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  create_cloudwatch_log_group     = true
  performance_insights_enabled    = true

  backup_retention_period = 7
  skip_final_snapshot     = false
  deletion_protection     = true

  allocated_storage     = 500
  max_allocated_storage = 1000

  vpc_security_group_ids = [module.postgres_security_group.security_group_id]

  create_db_parameter_group = true
}
