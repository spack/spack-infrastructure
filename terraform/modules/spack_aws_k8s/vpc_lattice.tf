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

# IAM role for the AWS Gateway API Controller for VPC Lattice (EKS Pod Identity)
resource "aws_iam_role" "vpc_lattice_controller" {
  name        = "VPCLatticeControllerIAMRole-${var.deployment_name}"
  description = "IAM Role for AWS Gateway API Controller for VPC Lattice"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEksAuthToAssumeRoleForPodIdentity"
        Effect = "Allow"
        Principal = {
          Service = "pods.eks.amazonaws.com"
        }
        Action = [
          "sts:AssumeRole",
          "sts:TagSession"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "vpc_lattice_controller" {
  role       = aws_iam_role.vpc_lattice_controller.name
  policy_arn = aws_iam_policy.vpc_lattice_controller.arn
}

resource "aws_eks_pod_identity_association" "vpc_lattice_controller" {
  cluster_name    = module.eks.cluster_name
  role_arn        = aws_iam_role.vpc_lattice_controller.arn
  namespace       = "aws-application-networking-system"
  service_account = "gateway-api-controller"
}
