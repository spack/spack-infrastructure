data "aws_iam_role" "terraform" {
  # This should already exist outside of Terraform, as it is used by Terraform to create all other resources.
  # If it doesn't, it should be manually created in the AWS console and given all necessary permissions.
  name = "terraform-role"
}

# IAM Roles
resource "aws_iam_role" "binary_cache_maintainer" {
  name = "BinaryCacheMaintainerRole"

  # Role assumption needs a grant on both sides: the BinaryCacheMaintainers group
  # is given sts:AssumeRole on this role below, and this trust policy names the
  # users allowed to make that call.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          AWS = [
            for user in local.binary_cache_maintainers :
            aws_iam_user.human[user].arn
          ]
        }
      }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "binary_cache_maintainer_full_access" {
  role       = aws_iam_role.binary_cache_maintainer.name
  policy_arn = module.spack_aws_k8s.binary_cache_full_access_policy_arn
}


# IAM Groups
resource "aws_iam_group" "custodians" {
  name = "Custodians"
}
resource "aws_iam_group" "binary_cache_maintainers" {
  name = "BinaryCacheMaintainers"
}
resource "aws_iam_group" "binary_cache_observers" {
  name = "BinaryCacheObservers"
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
# The mirror bucket policies themselves are declared alongside the buckets in
# modules/spack_aws_k8s/binary_mirrors.tf and surfaced here as module outputs.
# Observers read the protected mirror only.
resource "aws_iam_group_policy_attachment" "binary_cache_observers_protected_read_only" {
  group      = aws_iam_group.binary_cache_observers.name
  policy_arn = module.spack_aws_k8s.protected_binary_cache_read_only_policy_arn
}
# Maintainers read both mirrors; writes require assuming the role below.
resource "aws_iam_group_policy_attachment" "binary_cache_maintainers_protected_read_only" {
  group      = aws_iam_group.binary_cache_maintainers.name
  policy_arn = module.spack_aws_k8s.protected_binary_cache_read_only_policy_arn
}
resource "aws_iam_group_policy_attachment" "binary_cache_maintainers_pr_read_only" {
  group      = aws_iam_group.binary_cache_maintainers.name
  policy_arn = module.spack_aws_k8s.pr_binary_cache_read_only_policy_arn
}
resource "aws_iam_group_policy" "binary_cache_maintainers_assume_maintainer_role" {
  name  = "AssumeBinaryCacheMaintainerRole"
  group = aws_iam_group.binary_cache_maintainers.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = aws_iam_role.binary_cache_maintainer.arn
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
    "zack",
  ]
  binary_cache_maintainers = [
    "krattiger1",
    "tgamblin",
    "zack",
  ]
  binary_cache_observers = [
    "annehaley",
  ]
  eks_users = [
    "alecscott",
    "dan",
    "krattiger1",
    "krattiger1-eks-user",
    "tgamblin",
    "zack",
  ]
  # These users aren't in any groups.
  extra_users = [
    "john",
    "peter",
    "lpeyrala",
  ]

  all_human_users = distinct(concat(local.custodians, local.binary_cache_maintainers, local.binary_cache_observers, local.eks_users, local.extra_users))

  human_user_groups = {
    for user in distinct(concat(local.custodians, local.binary_cache_maintainers, local.binary_cache_observers, local.eks_users)) :
    user => concat(
      contains(local.custodians, user) ? [aws_iam_group.custodians.name] : [],
      contains(local.binary_cache_maintainers, user) ? [aws_iam_group.binary_cache_maintainers.name] : [],
      contains(local.binary_cache_observers, user) ? [aws_iam_group.binary_cache_observers.name] : [],
      contains(local.eks_users, user) ? [aws_iam_group.eks_users.name] : [],
    )
  }
}

resource "aws_iam_user_group_membership" "human" {
  for_each = local.human_user_groups

  user   = aws_iam_user.human[each.key].name
  groups = each.value
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

# Robot IAM users
resource "aws_iam_user" "e4s_cache" {
  name = "e4s-cache"
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
