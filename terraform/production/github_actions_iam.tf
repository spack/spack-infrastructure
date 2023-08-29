data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates.0.sha1_fingerprint]
}

resource "aws_iam_role" "github_actions" {
  name        = "GitHubActionsRole"
  description = "Managed by Terraform. IAM Role that a GitHub Actions runner can assume to authenticate with AWS."

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : aws_iam_openid_connect_provider.github_actions.arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringLike" : {
            "token.actions.githubusercontent.com:sub" : "repo:spack/spack-infrastructure:ref:refs/heads/*",
            "token.actions.githubusercontent.com:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  # Inline policy that allows GitHub actions to create AMIs using packer.
  # Docs: https://developer.hashicorp.com/packer/plugins/builders/amazon#iam-task-or-instance-role
  inline_policy {
    name = "PackerAMICreationPolicy"
    policy = jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Resource" : "*",
          "Action" : [
            "ec2:AttachVolume",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:CopyImage",
            "ec2:CreateImage",
            "ec2:CreateKeypair",
            "ec2:CreateSecurityGroup",
            "ec2:CreateSnapshot",
            "ec2:CreateTags",
            "ec2:CreateVolume",
            "ec2:DeleteKeyPair",
            "ec2:DeleteSecurityGroup",
            "ec2:DeleteSnapshot",
            "ec2:DeleteVolume",
            "ec2:DeregisterImage",
            "ec2:DescribeImageAttribute",
            "ec2:DescribeImages",
            "ec2:DescribeInstances",
            "ec2:DescribeInstanceStatus",
            "ec2:DescribeRegions",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeSnapshots",
            "ec2:DescribeSubnets",
            "ec2:DescribeTags",
            "ec2:DescribeVolumes",
            "ec2:DetachVolume",
            "ec2:GetPasswordData",
            "ec2:ModifyImageAttribute",
            "ec2:ModifyInstanceAttribute",
            "ec2:ModifySnapshotAttribute",
            "ec2:RegisterImage",
            "ec2:RunInstances",
            "ec2:StopInstances",
            "ec2:TerminateInstances"
          ]
        },
        {
          "Effect" : "Allow",
          "Action" : [
            "s3:GetObject"
          ],
          "Resource" : "arn:aws:s3:::amazon-eks/*"
        }
      ]
    })
  }

  # Inline policy that allows GitHub actions to read the Terraform state file
  inline_policy {
    name = "TerraformStateBucketAccessPolicy"
    policy = jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Resource" : "arn:aws:s3:::spack-terraform-state/terraform.tfstate",
          "Action" : ["s3:GetObject"]
      }]
    })
  }

  # Inline policy that allows Github Actions to describe the eks cluster
  inline_policy {
    name = "DescribeEKSClusterPolicy"
    policy = jsonencode({
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Resource" : module.production_cluster.cluster_arn,
          "Action" : [
            "eks:ListCluster",
            "eks:DescribeCluster",
          ]
        }
      ]
    })
  }
}
