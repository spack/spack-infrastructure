resource "aws_db_subnet_group" "analytics_db" {
  name       = "spack-analytics${local.suffix}"
  subnet_ids = module.vpc.private_subnets
}

resource "random_password" "analytics_db_password" {
  length           = 32
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

module "analytics_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.10.0"

  identifier = "spack-analytics${local.suffix}"

  engine               = "postgres"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = var.gitlab_db_instance_class

  # Credentials
  db_name                     = "analytics"
  username                    = "postgres"
  port                        = "5432"
  password                    = random_password.analytics_db_password.result
  manage_master_user_password = false

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.analytics_db.name

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

resource "kubectl_manifest" "webhook_analytics_db_secrets" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: webhook-handler-db
      namespace: custom
    stringData:
      analytics-postgresql-host: "${module.analytics_db.db_instance_address}"
      analytics-postgresql-password: "${random_password.analytics_db_password.result}"
  YAML
}
