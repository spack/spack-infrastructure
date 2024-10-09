resource "aws_db_subnet_group" "gitlab_db" {
  name       = "spack-gitlab${local.suffix}"
  subnet_ids = module.vpc.private_subnets
}

resource "random_password" "gitlab_db_password" {
  length = 20
}

module "gitlab_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.9.0"

  identifier = "spack-gitlab${local.suffix}"

  engine               = "postgres"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name                     = "gitlabhq_production"
  username                    = "postgres"
  port                        = "5432"
  manage_master_user_password = false
  password                    = random_password.gitlab_db_password.result

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.gitlab_db.name

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
}

module "postgres_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "5.1.2"

  name        = "spack-postgres${local.suffix}-sg"
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

# AWS secrets for Postgres
resource "kubectl_manifest" "gitlab_secrets" {
  # https://docs.gitlab.com/charts/charts/globals.html#connection
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: gitlab-secrets
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    stringData:
      postgres-password: "${random_password.gitlab_db_password.result}"
      values.yaml: |
        global:
          psql:
            host: "${module.gitlab_db.db_instance_address}"
  YAML
}

resource "kubectl_manifest" "gitlab_namespace" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Namespace
    metadata:
      name: gitlab
  YAML
}
