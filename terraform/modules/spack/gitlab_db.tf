# Retrieve the master password for the gitlab production database,
# since it has been changed since terraform created the RDS instance
data "aws_secretsmanager_secret" "gitlab_db_credentials" {
  arn = var.gitlab_db_master_credentials_secret
}
data "aws_secretsmanager_secret_version" "gitlab_db_credentials" {
  secret_id = data.aws_secretsmanager_secret.gitlab_db_credentials.id
}

# Determine the corresponding EC2 instance size, in order to retrieve the memory and vcpu size
data "aws_ec2_instance_type" "gitlab_db_instance_type" {
  instance_type = replace(var.gitlab_db_instance_class, "db.", "")
}

# Compute local values required in the gitlab_db module
locals {
  gitlab_db_master_password = jsondecode(data.aws_secretsmanager_secret_version.gitlab_db_credentials.secret_string)["password"]

  # Computed values for the parameters. The formulas for these values are taken from the
  # existing settings, encoding them here as the DSL for RDS parameters is insufficient
  max_logical_replication_workers = 4
  instance_type_memory_bytes      = data.aws_ec2_instance_type.gitlab_db_instance_type.memory_size * 1049000
  autovacuum_max_workers          = max(local.instance_type_memory_bytes / 64371566592, 3)
  max_parallel_workers            = max(data.aws_ec2_instance_type.gitlab_db_instance_type.default_vcpus / 2, 8)
  max_worker_processes            = sum([local.max_logical_replication_workers, local.autovacuum_max_workers, local.max_parallel_workers])

  # Conditionally specify params
  gitlab_db_params = [
    # Enable logical replication so CDCs can be run correctly
    {
      name         = "rds.logical_replication"
      value        = "1"
      apply_method = "pending-reboot"
    },
    # Ensure a timeout of at least 10000 (10s)
    {
      name         = "wal_sender_timeout"
      value        = "30000"
      apply_method = "pending-reboot"
    },
    # Explicitly set the max number of logical replication, autovacuum, and parallel workers.
    # The value of these parameters are stated here in order to encode them explicitly,
    # and are the values from the existing parameter group.
    {
      name         = "max_logical_replication_workers",
      value        = local.max_logical_replication_workers
      apply_method = "pending-reboot"
    },
    {
      name         = "autovacuum_max_workers",
      value        = local.autovacuum_max_workers
      apply_method = "pending-reboot"
    },
    {
      name         = "max_parallel_workers",
      value        = local.max_parallel_workers
      apply_method = "pending-reboot"
    },

    # The AWS docs highlight that this value should be at least the sum of the
    # 3 preceeding parameters, which is why they're defined here.
    {
      name         = "max_worker_processes"
      value        = local.max_worker_processes
      apply_method = "pending-reboot"
    }
  ]
}

module "gitlab_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.0.0"

  identifier = "gitlab-${var.deployment_name}"

  engine               = "postgres"
  engine_version       = "14.12"
  family               = "postgres14"
  major_engine_version = "14"
  instance_class       = var.gitlab_db_instance_class

  db_name                     = "gitlabhq_production"
  username                    = "postgres"
  port                        = "5432"
  password                    = local.gitlab_db_master_password
  manage_master_user_password = false

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

  # Set parameters in the automatically created parameter group to allow replication
  create_db_parameter_group = true
  parameters                = local.gitlab_db_params
}

module "postgres_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "5.1.2"

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
