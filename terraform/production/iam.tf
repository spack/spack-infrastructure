data "aws_iam_role" "terraform" {
  # This should already exist outside of Terraform, as it is used by Terraform to create all other resources.
  # If it doesn't, it should be manually created in the AWS console and given all necessary permissions.
  name = "terraform-role"
}

# IAM Groups
resource "aws_iam_group" "administrators" {
  name = "Administrators"
}
resource "aws_iam_group" "custodians" {
  name = "Custodians"
}
resource "aws_iam_group" "e4s_cache" {
  name = "e4s-cache"
}
resource "aws_iam_group" "eks_users" {
  name = "EKSUsers"
}
resource "aws_iam_group_policy_attachment" "administrators_assume_eks_access_role" {
  group      = aws_iam_group.administrators.name
  policy_arn = aws_iam_policy.assume_eks_access_role.arn
}
resource "aws_iam_group_policy_attachment" "administrators_administrator_access" {
  group      = aws_iam_group.administrators.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
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
resource "aws_iam_group_policy_attachment" "e4s_cache_allow_bucket_list" {
  group      = aws_iam_group.e4s_cache.name
  policy_arn = aws_iam_policy.allow_group_to_see_bucket_list_in_the_console.arn
}
resource "aws_iam_group_policy_attachment" "eks_users_assume_eks_access_role" {
  group      = aws_iam_group.eks_users.name
  policy_arn = aws_iam_policy.assume_eks_access_role.arn
}
resource "aws_iam_group_policy" "eks_users_eks_cluster_access" {
  name  = "EKS-Cluster-Access"
  group = aws_iam_group.eks_users.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PermissionToAssumeEKSAccessRole"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = "arn:aws:iam::588562868276:role/SpackEKSClusterAccess20230124203318984800000001"
      }
    ]
  })
}
resource "aws_iam_user_group_membership" "alecscott" {
  user = aws_iam_user.alecscott.name
  groups = [
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "dan" {
  user = aws_iam_user.dan.name
  groups = [
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "e4s_cache" {
  user = aws_iam_user.e4s_cache.name
  groups = [
    aws_iam_group.e4s_cache.name,
  ]
}
resource "aws_iam_user_group_membership" "jacob" {
  user = aws_iam_user.jacob.name
  groups = [
    aws_iam_group.custodians.name,
  ]
}
resource "aws_iam_user_group_membership" "krattiger1" {
  user = aws_iam_user.krattiger1.name
  groups = [
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "krattiger1_eks_user" {
  user = aws_iam_user.krattiger1_eks_user.name
  groups = [
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "mike" {
  user = aws_iam_user.mike.name
  groups = [
    aws_iam_group.custodians.name,
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "tgamblin" {
  user = aws_iam_user.tgamblin.name
  groups = [
    aws_iam_group.eks_users.name,
  ]
}
resource "aws_iam_user_group_membership" "zack" {
  user = aws_iam_user.zack.name
  groups = [
    aws_iam_group.custodians.name,
    aws_iam_group.eks_users.name,
  ]
}


# Human IAM users
resource "aws_iam_user" "dan" {
  name = "dan"
}
resource "aws_iam_user" "jacob" {
  name = "jacob"
}
resource "aws_iam_user" "krattiger1" {
  name = "krattiger1"
}
resource "aws_iam_user" "krattiger1_eks_user" {
  name = "krattiger1-eks-user"
}
resource "aws_iam_user" "mike" {
  name = "mike"
}
resource "aws_iam_user" "zack" {
  name = "zack"
}
resource "aws_iam_user" "alecscott" {
  name = "alecscott"
}
resource "aws_iam_user" "lpeyrala" {
  name = "lpeyrala"
}
resource "aws_iam_user" "tgamblin" {
  name = "tgamblin"
}
# TODO: can we remove these?
resource "aws_iam_user_policy_attachment" "tgamblin_route53" {
  user       = aws_iam_user.tgamblin.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonRoute53FullAccess"
}
resource "aws_iam_user_policy_attachment" "tgamblin_s3" {
  user       = aws_iam_user.tgamblin.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}


# Robot IAM users
resource "aws_iam_user" "cray_binary_mirror" {
  name = "cray-binary-mirror"
}
resource "aws_iam_user" "cz_source_mirror_sync" {
  name = "cz-source-mirror-sync"
}
resource "aws_iam_user" "e4s_cache" {
  name = "e4s-cache"
}
resource "aws_iam_user" "metabase_ses_smtp_user" {
  name = "metabase-ses-smtp-user.20230503-153955"
}
resource "aws_iam_user" "spack_bootstrap_mirror_upload" {
  name = "spack-bootstrap-mirror-upload"
}
resource "aws_iam_user_policy_attachment" "cray_binary_mirror_crud" {
  user       = aws_iam_user.cray_binary_mirror.name
  policy_arn = aws_iam_policy.crud_access_to_spack_binaries_cray.arn
}
resource "aws_iam_user_policy_attachment" "cz_source_mirror_sync_put_delete" {
  user       = aws_iam_user.cz_source_mirror_sync.name
  policy_arn = aws_iam_policy.put_and_delete_from_spack_llnl_source_mirror.arn
}
resource "aws_iam_user_policy_attachment" "spack_bootstrap_mirror_upload_put_delete" {
  user       = aws_iam_user.spack_bootstrap_mirror_upload.name
  policy_arn = aws_iam_policy.put_and_delete_from_spack_llnl_bootstrap_mirror.arn
}
resource "aws_iam_user_policy_attachment" "tgamblin_source_mirror" {
  user       = aws_iam_user.tgamblin.name
  policy_arn = aws_iam_policy.put_and_delete_from_spack_llnl_source_mirror.arn
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


# IAM policies (applied to users and groups)
resource "aws_iam_policy" "crud_access_to_spack_binaries_cray" {
  name = "CRUDAccessToSpackBinariesCray"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VisualEditor0"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:GetObjectAttributes",
          "s3:DeleteObject",
        ]
        Resource = ["arn:aws:s3:::spack-binaries-cray/*"]
      },
      {
        Sid      = "Statement1"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["arn:aws:s3:::spack-binaries-cray"]
      }
    ]
  })
}
resource "aws_iam_policy" "put_and_delete_from_spack_llnl_source_mirror" {
  name = "PutAndDeleteFromSpackLLNLSourceMirror"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "VisualEditor0"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "arn:aws:s3:::spack-llnl-mirror/*"
      },
      {
        Sid      = "VisualEditor1"
        Effect   = "Allow"
        Action   = "s3:DeleteObject"
        Resource = "arn:aws:s3:::spack-llnl-mirror/*"
      },
      {
        Sid      = "newstatementmay302025"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = "arn:aws:s3:::spack-llnl-mirror/*"
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


# Outdated stuff. TODO: remove
resource "aws_iam_policy" "assume_eks_access_role" {
  name = "AssumeEKSAccessRole"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PermissionToAssumeEKSAccessRole"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = "arn:aws:iam::588562868276:role/Spack-EKS-Cluster-Access"
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
