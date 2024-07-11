module "cdash_db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "5.9.0"

  identifier = "cdash-${var.deployment_name}"

  engine               = "mysql"
  engine_version       = "8.0.35"
  family               = "mysql8.0"
  major_engine_version = "8.0"
  instance_class       = var.cdash_db_instance_class

  username = "admin"
  port     = "3306"

  publicly_accessible  = false
  db_subnet_group_name = aws_db_subnet_group.spack.name

  maintenance_window           = "Sun:00:00-Sun:03:00"
  backup_window                = "03:00-06:00"
  create_cloudwatch_log_group  = true
  performance_insights_enabled = var.deployment_name == "prod"

  backup_retention_period = 7
  skip_final_snapshot     = true
  deletion_protection     = true

  allocated_storage     = 100
  max_allocated_storage = 300

  vpc_security_group_ids = [module.mysql_security_group.security_group_id]
}

module "mysql_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "4.16.2"

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
