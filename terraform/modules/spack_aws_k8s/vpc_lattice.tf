data "aws_ec2_managed_prefix_list" "cluster_prefix_list" {
  name = "com.amazonaws.${var.region}.vpc-lattice"
}
data "aws_ec2_managed_prefix_list" "cluster_prefix_list_ipv6" {
  name = "com.amazonaws.${var.region}.ipv6.vpc-lattice"
}

# VPC Lattice controller IAM policy
resource "aws_iam_policy" "vpc_lattice_controller" {
  name        = "VPCLatticeControllerIAMPolicy"
  description = "IAM policy for the VPC Lattice controller"

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "vpc-lattice:*",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeTags",
          "ec2:DescribeSecurityGroups",
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:DescribeLogGroups",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "tag:GetResources",
          "firehose:TagDeliveryStream",
          "s3:GetBucketPolicy",
          "s3:PutBucketPolicy",
          "tag:TagResources",
          "tag:UntagResources"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : "iam:CreateServiceLinkedRole",
        "Resource" : "arn:aws:iam::*:role/aws-service-role/vpc-lattice.amazonaws.com/AWSServiceRoleForVpcLattice",
        "Condition" : {
          "StringLike" : {
            "iam:AWSServiceName" : "vpc-lattice.amazonaws.com"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : "iam:CreateServiceLinkedRole",
        "Resource" : "arn:aws:iam::*:role/aws-service-role/delivery.logs.amazonaws.com/AWSServiceRoleForLogDelivery",
        "Condition" : {
          "StringLike" : {
            "iam:AWSServiceName" : "delivery.logs.amazonaws.com"
          }
        }
      }
    ]
  })
}
