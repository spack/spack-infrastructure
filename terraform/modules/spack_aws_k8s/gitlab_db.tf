locals {
  gitlab_db_username = "postgres"
}

resource "aws_db_subnet_group" "gitlab_db" {
  name       = "spack-gitlab${local.suffix}"
  subnet_ids = module.vpc.private_subnets
}

resource "random_password" "gitlab_db_password" {
  length = 20
}

module "gitlab_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.10.0"

  identifier = "spack-gitlab${local.suffix}"

  engine               = "postgres"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name                     = "gitlabhq_production"
  username                    = local.gitlab_db_username
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
  storage_type          = "gp3"
  iops                  = 12000 # 12,000 is the minimum IOPs for gp3 storage. We can increase this as needed.
  storage_throughput    = 500   # 500 is the minimum throughput for gp3 storage. We can increase this as needed.

  vpc_security_group_ids = [module.postgres_security_group.security_group_id]
}

module "postgres_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "5.2.0"

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

# RDS Proxy (connection pooling)
data "aws_kms_alias" "secretsmanager" {
  name = "alias/aws/secretsmanager"
}

resource "aws_secretsmanager_secret" "gitlab_db" {
  name        = "spack-gitlab${local.suffix}-db-proxy-credentials"
  description = "GitLab database superuser, ${local.gitlab_db_username}, database connection values"
  kms_key_id  = data.aws_kms_alias.secretsmanager.id
}

resource "aws_secretsmanager_secret_version" "gitlab_db" {
  secret_id = aws_secretsmanager_secret.gitlab_db.id
  secret_string = jsonencode({
    username = local.gitlab_db_username
    password = random_password.gitlab_db_password.result
  })
}


module "gitlab_db_proxy" {
  source  = "terraform-aws-modules/rds-proxy/aws"
  version = "3.1.0"

  name                   = "spack-gitlab${local.suffix}"
  iam_role_name          = "spack-gitlab${local.suffix}-db-proxy-role"
  vpc_subnet_ids         = module.vpc.private_subnets
  vpc_security_group_ids = [module.gitlab_db_proxy_sg.security_group_id]

  auth = {
    (aws_secretsmanager_secret.gitlab_db.name) = {
      auth_scheme               = "SECRETS"
      client_password_auth_type = "POSTGRES_SCRAM_SHA_256"
      description               = aws_secretsmanager_secret.gitlab_db.description
      iam_auth                  = "DISABLED"
      secret_arn                = aws_secretsmanager_secret.gitlab_db.arn
    }
  }

  engine_family = "POSTGRESQL"
  debug_logging = false

  target_db_instance     = true
  db_instance_identifier = module.gitlab_db.db_instance_identifier
}


module "gitlab_db_proxy_sg" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "5.2.0"

  name        = "spack-gitlab${local.suffix}-rds-proxy-sg"
  description = "GitLab ${var.deployment_name} PostgreSQL RDS Proxy security group"
  vpc_id      = module.vpc.vpc_id

  revoke_rules_on_delete = true

  ingress_with_cidr_blocks = [
    {
      description = "Private subnet PostgreSQL access"
      rule        = "postgresql-tcp"
      cidr_blocks = join(",", module.vpc.private_subnets_cidr_blocks)
    }
  ]

  egress_with_cidr_blocks = [
    {
      description = "Database subnet PostgreSQL access"
      rule        = "postgresql-tcp"
      cidr_blocks = join(",", module.vpc.private_subnets_cidr_blocks)
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
            host: "${module.gitlab_db_proxy.proxy_endpoint}"
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
