import {
  to = aws_iam_policy.assume_eks_access_role
  id = "arn:aws:iam::588562868276:policy/AssumeEKSAccessRole"
}

import {
  to = aws_iam_policy.allow_group_to_see_bucket_list_in_the_console
  id = "arn:aws:iam::588562868276:policy/AllowGroupToSeeBucketListInTheConsole"
}

import {
  to = aws_iam_policy.crud_access_to_spack_binaries_cray
  id = "arn:aws:iam::588562868276:policy/CRUDAccessToSpackBinariesCray"
}

import {
  to = aws_iam_policy.put_and_delete_from_spack_llnl_source_mirror
  id = "arn:aws:iam::588562868276:policy/PutAndDeleteFromSpackLLNLSourceMirror"
}

import {
  to = aws_iam_policy.put_and_delete_from_spack_llnl_bootstrap_mirror
  id = "arn:aws:iam::588562868276:policy/PutAndDeleteFromSpackLLNLBootstrapMirror"
}

# Groups
import {
  to = aws_iam_group.administrators
  id = "Administrators"
}

import {
  to = aws_iam_group.custodians
  id = "Custodians"
}

import {
  to = aws_iam_group.e4s_cache
  id = "e4s-cache"
}

import {
  to = aws_iam_group.eks_users
  id = "EKSUsers"
}

# Group policy attachments
import {
  to = aws_iam_group_policy_attachment.administrators_assume_eks_access_role
  id = "Administrators/arn:aws:iam::588562868276:policy/AssumeEKSAccessRole"
}

import {
  to = aws_iam_group_policy_attachment.administrators_administrator_access
  id = "Administrators/arn:aws:iam::aws:policy/AdministratorAccess"
}

import {
  to = aws_iam_group_policy_attachment.custodians_iam_read_only_access
  id = "Custodians/arn:aws:iam::aws:policy/IAMReadOnlyAccess"
}

import {
  to = aws_iam_group_policy_attachment.custodians_rds_read_only_access
  id = "Custodians/arn:aws:iam::aws:policy/AmazonRDSReadOnlyAccess"
}

import {
  to = aws_iam_group_policy_attachment.e4s_cache_allow_bucket_list
  id = "e4s-cache/arn:aws:iam::588562868276:policy/AllowGroupToSeeBucketListInTheConsole"
}

import {
  to = aws_iam_group_policy_attachment.eks_users_assume_eks_access_role
  id = "EKSUsers/arn:aws:iam::588562868276:policy/AssumeEKSAccessRole"
}

# Group inline policies
import {
  to = aws_iam_group_policy.custodians_assume_terraform_role
  id = "Custodians:AssumeTerraformRole"
}

import {
  to = aws_iam_group_policy.eks_users_eks_cluster_access
  id = "EKSUsers:EKS-Cluster-Access"
}

# User group memberships
import {
  to = aws_iam_user_group_membership.alecscott
  id = "alecscott/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.dan
  id = "dan/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.e4s_cache
  id = "e4s-cache/e4s-cache"
}

import {
  to = aws_iam_user_group_membership.jacob
  id = "jacob/Custodians"
}

import {
  to = aws_iam_user_group_membership.krattiger1
  id = "krattiger1/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.krattiger1_eks_user
  id = "krattiger1-eks-user/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.mike
  id = "mike/Custodians/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.tgamblin
  id = "tgamblin/EKSUsers"
}

import {
  to = aws_iam_user_group_membership.zack
  id = "zack/Custodians/EKSUsers"
}

# Users
import {
  to = aws_iam_user.alecscott
  id = "alecscott"
}

import {
  to = aws_iam_user.cray_binary_mirror
  id = "cray-binary-mirror"
}

import {
  to = aws_iam_user.cz_source_mirror_sync
  id = "cz-source-mirror-sync"
}

import {
  to = aws_iam_user.dan
  id = "dan"
}

import {
  to = aws_iam_user.e4s_cache
  id = "e4s-cache"
}

import {
  to = aws_iam_user.jacob
  id = "jacob"
}

import {
  to = aws_iam_user.krattiger1
  id = "krattiger1"
}

import {
  to = aws_iam_user.krattiger1_eks_user
  id = "krattiger1-eks-user"
}

import {
  to = aws_iam_user.lpeyrala
  id = "lpeyrala"
}

import {
  to = aws_iam_user.metabase_ses_smtp_user
  id = "metabase-ses-smtp-user.20230503-153955"
}

import {
  to = aws_iam_user.mike
  id = "mike"
}

import {
  to = aws_iam_user.spack_bootstrap_mirror_upload
  id = "spack-bootstrap-mirror-upload"
}

import {
  to = aws_iam_user.tgamblin
  id = "tgamblin"
}

import {
  to = aws_iam_user.zack
  id = "zack"
}

# User policy attachments
import {
  to = aws_iam_user_policy_attachment.cray_binary_mirror_crud
  id = "cray-binary-mirror/arn:aws:iam::588562868276:policy/CRUDAccessToSpackBinariesCray"
}

import {
  to = aws_iam_user_policy_attachment.cz_source_mirror_sync_put_delete
  id = "cz-source-mirror-sync/arn:aws:iam::588562868276:policy/PutAndDeleteFromSpackLLNLSourceMirror"
}

import {
  to = aws_iam_user_policy_attachment.spack_bootstrap_mirror_upload_put_delete
  id = "spack-bootstrap-mirror-upload/arn:aws:iam::588562868276:policy/PutAndDeleteFromSpackLLNLBootstrapMirror"
}

import {
  to = aws_iam_user_policy_attachment.tgamblin_source_mirror
  id = "tgamblin/arn:aws:iam::588562868276:policy/PutAndDeleteFromSpackLLNLSourceMirror"
}

import {
  to = aws_iam_user_policy_attachment.tgamblin_route53
  id = "tgamblin/arn:aws:iam::aws:policy/AmazonRoute53FullAccess"
}

import {
  to = aws_iam_user_policy_attachment.tgamblin_s3
  id = "tgamblin/arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# User inline policies
import {
  to = aws_iam_user_policy.e4s_cache_read_write
  id = "e4s-cache:ReadWriteE4SCache"
}

import {
  to = aws_iam_user_policy.metabase_ses_sending_access
  id = "metabase-ses-smtp-user.20230503-153955:AmazonSesSendingAccess"
}
