resource "aws_db_subnet_group" "cdash_db" {
  name       = "spack-cdash${local.suffix}"
  subnet_ids = module.vpc.private_subnets
}

resource "random_password" "cdash_db_password" {
  length           = 32
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

module "cdash_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.10.0"

  identifier = "spack-cdash${local.suffix}"

  engine               = "mysql"
  engine_version       = "8.0.40"
  family               = "mysql8.0"
  major_engine_version = "8.0"
  instance_class       = var.cdash_db_instance_class

  username                    = "admin"
  port                        = "3306"
  password                    = random_password.cdash_db_password.result
  manage_master_user_password = false

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.cdash_db.name

  maintenance_window           = "Sun:00:00-Sun:03:00"
  backup_window                = "03:00-06:00"
  create_cloudwatch_log_group  = true
  performance_insights_enabled = var.deployment_name == "prod"

  backup_retention_period = 7
  skip_final_snapshot     = true
  deletion_protection     = true

  allocated_storage  = 300
  storage_type       = "gp3"
  iops               = 3000 # 3,000 is the minimum IOPs for <400 GB storage. We can increase this as needed.
  storage_throughput = 125  # 125 is the minimum throughput for <400 GB storage. We can increase this as needed.

  vpc_security_group_ids = [module.mysql_security_group.security_group_id]
}

module "mysql_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "5.2.0"

  name        = "mysql_sg"
  description = "Security group for RDS MySQL database"
  vpc_id      = module.vpc.vpc_id

  ingress_with_cidr_blocks = [
    {
      from_port   = 3306
      to_port     = 3306
      protocol    = "tcp"
      description = "MySQL access from within VPC"
      cidr_blocks = module.vpc.vpc_cidr_block
    },
  ]
}
