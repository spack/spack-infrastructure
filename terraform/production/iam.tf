data "aws_iam_role" "terraform" {
  # This should already exist outside of Terraform, as it is used by Terraform to create all other resources.
  # If it doesn't, it should be manually created in the AWS console and given all necessary permissions.
  name = "terraform-role"
}

# IAM Groups
resource "aws_iam_group" "custodians" {
  name = "Custodians"
}
resource "aws_iam_group" "e4s_cache" {
  name = "e4s-cache"
}
resource "aws_iam_group" "eks_users" {
  name = "EKSUsers"
}
resource "aws_iam_group_policy_attachment" "custodians_iam_read_only_access" {
  group      = aws_iam_group.custodians.name
  policy_arn = "arn:aws:iam::aws:policy/IAMReadOnlyAccess"
}
resource "aws_iam_group_policy_attachment" "custodians_rds_read_only_access" {
  group      = aws_iam_group.custodians.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonRDSReadOnlyAccess"
}
resource "aws_iam_group_policy" "custodians_assume_terraform_role" {
  name  = "AssumeTerraformRole"
  group = aws_iam_group.custodians.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = data.aws_iam_role.terraform.arn
      }
    ]
  })
}
resource "aws_iam_group_policy" "custodians_rds_snapshots" {
  name  = "RDSSnapshots"
  group = aws_iam_group.custodians.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CreateAndListRDSSnapshots"
        Effect = "Allow"
        Action = [
          "rds:CreateDBSnapshot",
          "rds:DescribeDBSnapshots",
          "rds:ListTagsForResource",
        ]
        Resource = "*"
      }
    ]
  })
}
resource "aws_iam_group_policy" "custodians_waf_logs_read_only" {
  name  = "WafLogsReadOnly"
  group = aws_iam_group.custodians.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListWafLogGroups"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
      {
        Sid    = "ReadAndQueryWafLogs"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
        ]
        Resource = "arn:aws:logs:us-east-1:588562868276:log-group:aws-waf-logs-*:*"
      }
    ]
  })
}
resource "aws_iam_group_policy" "custodians_ebs_snapshots" {
  name  = "EBSSnapshots"
  group = aws_iam_group.custodians.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CreateAndListEBSSnapshots"
        Effect = "Allow"
        Action = [
          "ec2:CreateSnapshot",
          "ec2:DescribeSnapshots",
          "ec2:DescribeVolumes",
        ]
        Resource = "*"
      }
    ]
  })
}
resource "aws_iam_group_policy_attachment" "e4s_cache_allow_bucket_list" {
  group      = aws_iam_group.e4s_cache.name
  policy_arn = aws_iam_policy.allow_group_to_see_bucket_list_in_the_console.arn
}
resource "aws_iam_user_group_membership" "e4s_cache" {
  user = aws_iam_user.e4s_cache.name
  groups = [
    aws_iam_group.e4s_cache.name,
  ]
}

# ############################
# Human IAM user definitions
# ############################

locals {
  custodians = [
    "jacob",
    "mike",
    "zack",
  ]
  eks_users = [
    "alecscott",
    "dan",
    "krattiger1",
    "krattiger1-eks-user",
    "mike",
    "tgamblin",
    "zack",
  ]
  # These users aren't in any groups.
  extra_users = [
    "john",
    "peter",
    "lpeyrala",
  ]

  all_human_users = distinct(concat(local.custodians, local.eks_users, local.extra_users))

  human_user_groups = {
    for user in distinct(concat(local.custodians, local.eks_users)) :
    user => concat(
      contains(local.custodians, user) ? [aws_iam_group.custodians.name] : [],
      contains(local.eks_users, user) ? [aws_iam_group.eks_users.name] : [],
    )
  }
}

resource "aws_iam_user_group_membership" "human" {
  for_each = local.human_user_groups

  user   = aws_iam_user.human[each.key].name
  groups = each.value
}

moved {
  from = aws_iam_user_group_membership.alecscott
  to   = aws_iam_user_group_membership.human["alecscott"]
}

moved {
  from = aws_iam_user_group_membership.dan
  to   = aws_iam_user_group_membership.human["dan"]
}

moved {
  from = aws_iam_user_group_membership.jacob
  to   = aws_iam_user_group_membership.human["jacob"]
}

moved {
  from = aws_iam_user_group_membership.krattiger1
  to   = aws_iam_user_group_membership.human["krattiger1"]
}

moved {
  from = aws_iam_user_group_membership.krattiger1_eks_user
  to   = aws_iam_user_group_membership.human["krattiger1-eks-user"]
}

moved {
  from = aws_iam_user_group_membership.mike
  to   = aws_iam_user_group_membership.human["mike"]
}

moved {
  from = aws_iam_user_group_membership.tgamblin
  to   = aws_iam_user_group_membership.human["tgamblin"]
}

moved {
  from = aws_iam_user_group_membership.zack
  to   = aws_iam_user_group_membership.human["zack"]
}

resource "aws_iam_user" "human" {
  for_each = toset(local.all_human_users)
  name     = each.value

  lifecycle {
    ignore_changes = [
      tags
    ]
  }
}

moved {
  from = aws_iam_user.dan
  to   = aws_iam_user.human["dan"]
}

moved {
  from = aws_iam_user.jacob
  to   = aws_iam_user.human["jacob"]
}

moved {
  from = aws_iam_user.john
  to   = aws_iam_user.human["john"]
}

moved {
  from = aws_iam_user.peter
  to   = aws_iam_user.human["peter"]
}

moved {
  from = aws_iam_user.krattiger1
  to   = aws_iam_user.human["krattiger1"]
}

moved {
  from = aws_iam_user.krattiger1_eks_user
  to   = aws_iam_user.human["krattiger1-eks-user"]
}

moved {
  from = aws_iam_user.mike
  to   = aws_iam_user.human["mike"]
}

moved {
  from = aws_iam_user.zack
  to   = aws_iam_user.human["zack"]
}

moved {
  from = aws_iam_user.alecscott
  to   = aws_iam_user.human["alecscott"]
}

moved {
  from = aws_iam_user.lpeyrala
  to   = aws_iam_user.human["lpeyrala"]
}

moved {
  from = aws_iam_user.tgamblin
  to   = aws_iam_user.human["tgamblin"]
}

# Robot IAM users
resource "aws_iam_user" "e4s_cache" {
  name = "e4s-cache"
}
resource "aws_iam_user" "metabase_ses_smtp_user" {
  name = "metabase-ses-smtp-user.20230503-153955"
}
resource "aws_iam_user" "spack_bootstrap_mirror_upload" {
  name = "spack-bootstrap-mirror-upload"
}
resource "aws_iam_user_policy_attachment" "spack_bootstrap_mirror_upload_put_delete" {
  user       = aws_iam_user.spack_bootstrap_mirror_upload.name
  policy_arn = aws_iam_policy.put_and_delete_from_spack_llnl_bootstrap_mirror.arn
}
resource "aws_iam_user_policy" "e4s_cache_read_write" {
  name = "ReadWriteE4SCache"
  user = aws_iam_user.e4s_cache.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListObjectsInBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["arn:aws:s3:::cache.e4s.io"]
      },
      {
        Sid      = "AllObjectActions"
        Effect   = "Allow"
        Action   = "s3:*Object"
        Resource = ["arn:aws:s3:::cache.e4s.io/*"]
      }
    ]
  })
}
resource "aws_iam_user_policy" "metabase_ses_sending_access" {
  name = "AmazonSesSendingAccess"
  user = aws_iam_user.metabase_ses_smtp_user.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ses:SendRawEmail"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_policy" "put_and_delete_from_spack_llnl_bootstrap_mirror" {
  name = "PutAndDeleteFromSpackLLNLBootstrapMirror"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "VisualEditor0"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "arn:aws:s3:::spack-llnl-mirror/bootstrap/*"
      },
      {
        Sid      = "VisualEditor1"
        Effect   = "Allow"
        Action   = "s3:DeleteObject"
        Resource = "arn:aws:s3:::spack-llnl-mirror/bootstrap/*"
      }
    ]
  })
}

resource "aws_iam_policy" "allow_group_to_see_bucket_list_in_the_console" {
  name = "AllowGroupToSeeBucketListInTheConsole"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowGroupToSeeBucketListInTheConsole"
        Action   = ["s3:ListAllMyBuckets"]
        Effect   = "Allow"
        Resource = ["arn:aws:s3:::*"]
      }
    ]
  })
}
