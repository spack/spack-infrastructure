locals {
  cdash_db_name = "cdash"
  cdash_db_user = "cdash"
  cdash_db_port = "5432"
}

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

  identifier = "spack-cdash-postgres${local.suffix}"

  engine               = "postgres"
  family               = "postgres17"
  major_engine_version = "17"
  instance_class       = var.cdash_db_instance_class

  db_name                     = local.cdash_db_name
  username                    = local.cdash_db_user
  password                    = random_password.cdash_db_password.result
  port                        = local.cdash_db_port
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

  allocated_storage  = 400
  storage_type       = "gp3"
  iops               = 12000 # 3,000 is the minimum IOPs for <400 GB storage. We can increase this as needed.
  storage_throughput = 500   # 500 is the minimum throughput for >=400 GB storage. We can increase this as needed.

  vpc_security_group_ids = [module.postgres_security_group.security_group_id]
}

resource "aws_s3_bucket" "cdash" {
  bucket = "spack-cdash${local.suffix}"
  lifecycle {
    prevent_destroy = true
  }
}

# Bucket policy that prevents deletion of CDash bucket.
resource "aws_s3_bucket_policy" "cdash" {
  bucket = aws_s3_bucket.cdash.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Principal" : "*"
        "Effect" : "Deny",
        "Action" : [
          "s3:DeleteBucket",
        ],
        "Resource" : aws_s3_bucket.cdash.arn
      }
    ]
  })
}

resource "aws_iam_role" "cdash" {
  name        = "CDashS3Role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. Role for CDash to assume so that it can access relevant S3 buckets."
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn,
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "cdash" {
  name        = "CDashS3Role-${var.deployment_name}-${var.deployment_stage}"
  description = "Managed by Terraform. Grants required permissions for CDash to read/write to relevant S3 buckets."
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ],
        "Resource" : aws_s3_bucket.cdash.arn
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:DeleteObject",
          "s3:DeleteObjectVersion",
          "s3:GetObject",
          "s3:GetObjectAcl",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:ReplicateObject"
        ],
        "Resource" : [
          aws_s3_bucket.cdash.arn,
          "${aws_s3_bucket.cdash.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cdash" {
  role       = aws_iam_role.cdash.name
  policy_arn = aws_iam_policy.cdash.arn
}

resource "kubectl_manifest" "cdash_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: cdash
      namespace: cdash
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.cdash.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.cdash,
  ]
}

resource "kubectl_manifest" "cdash_s3_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: cdash-s3
      namespace: cdash
    stringData:
      region: "${data.aws_region.current.name}"
      bucket: "${aws_s3_bucket.cdash.id}"
  YAML
}

resource "kubectl_manifest" "cdash_db_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: cdash-db
      namespace: cdash
    stringData:
      host: "${module.cdash_db.db_instance_address}"
      database: "${local.cdash_db_name}"
      username: "${local.cdash_db_user}"
      password: "${random_password.cdash_db_password.result}"
      port: "${local.cdash_db_port}"
  YAML
}
