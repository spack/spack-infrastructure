resource "aws_db_subnet_group" "this" {
  name       = "gitaly-rds-group"
  subnet_ids = var.db_subnet_ids
}

resource "random_password" "postgres_password" {
  length           = 64
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_db_instance" "this" {
  identifier                = "gitaly-database-${var.deployment_name}"
  allocated_storage         = 10
  backup_retention_period   = 7
  db_subnet_group_name      = aws_db_subnet_group.this.name
  deletion_protection       = true
  engine                    = "postgres"
  engine_version            = "15.3"
  final_snapshot_identifier = "gitalyhqproduction"
  instance_class            = "db.t4g.medium" # equivalent to c5.large. See https://docs.gitlab.com/ee/administration/reference_architectures/3k_users.html
  multi_az                  = true
  # TODO:
  # storage_type              = "gp3"
  # iops                      = 8000 # https://docs.gitlab.com/ee/administration/reference_architectures/3k_users.html#configure-gitaly
  username                  = "gitaly"
  password                  = random_password.postgres_password.result
  publicly_accessible       = false
  skip_final_snapshot       = false
  vpc_security_group_ids    = [aws_security_group.this.id]
}

resource "aws_security_group" "this" {
  name        = "gitaly-rds-${var.deployment_name}-sg"
  vpc_id      = var.vpc_id
  description = "Security group for the gitaly RDS DB"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    description = "PostgreSQL access from within VPC"
    cidr_blocks = [var.vpc_cidr]
  }
}
