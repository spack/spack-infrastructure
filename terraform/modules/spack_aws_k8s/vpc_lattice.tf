data "aws_ec2_managed_prefix_list" "cluster_prefix_list" {
  name = "com.amazonaws.${var.region}.vpc-lattice"
}
data "aws_ec2_managed_prefix_list" "cluster_prefix_list_ipv6" {
  name = "com.amazonaws.${var.region}.ipv6.vpc-lattice"
}

# VPC Lattice service network for the spack Gateway. The AWS Gateway API controller
# looks up a service network by the Gateway's name (e.g. Gateway "spack-gateway" -> service network "spack-gateway").
resource "aws_vpclattice_service_network" "spack_gateway" {
  name      = "${local.eks_cluster_name}-gateway"
  auth_type = "NONE"
}

resource "aws_vpclattice_service_network_vpc_association" "spack_gateway" {
  service_network_identifier = aws_vpclattice_service_network.spack_gateway.id
  vpc_identifier             = module.vpc.vpc_id
  # security_group_ids = [module.eks.cluster_primary_security_group_id]
}

resource "aws_security_group_rule" "vpc_lattice_ingress_all" {
  type      = "ingress"
  from_port = "-1"
  to_port   = "-1"
  protocol  = "-1"
  prefix_list_ids = [
    data.aws_ec2_managed_prefix_list.cluster_prefix_list.id,
    data.aws_ec2_managed_prefix_list.cluster_prefix_list_ipv6.id
  ]
  security_group_id = module.eks.cluster_primary_security_group_id
}
# TODO: May be needed? Didn't seem to affect anything when I tried it.
# resource "aws_security_group_rule" "vpc_lattice_ingress_nodes" {
#   type      = "ingress"
#   from_port = "-1"
#   to_port   = "-1"
#   protocol  = "-1"
#   prefix_list_ids = [
#     data.aws_ec2_managed_prefix_list.cluster_prefix_list.id,
#     data.aws_ec2_managed_prefix_list.cluster_prefix_list_ipv6.id
#   ]
#   security_group_id = module.eks.node_security_group_id
#   description       = "Allow VPC Lattice traffic to reach pods on worker nodes"
# }

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

resource "kubectl_manifest" "external_dns_namespace" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Namespace
    metadata:
      name: external-dns
  YAML
}

#
# External DNS Helm Release
resource "helm_release" "external_dns" {
  namespace        = "external-dns"
  create_namespace = false

  name       = "external-dns"
  repository = "https://kubernetes-sigs.github.io/external-dns/"
  chart      = "external-dns"
  version    = "1.20.0"
  values = [
    <<-EOT
    serviceAccount:
      create: true
    sources:
      - gateway-httproute
    env:
      - name: AWS_DEFAULT_REGION
        value: ${var.region}
    EOT
  ]
}

data "aws_iam_policy_document" "eks_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
    actions = [
      "sts:AssumeRole",
      "sts:TagSession"
    ]
  }
}

resource "aws_iam_role" "external_dns_pod_identity" {
  name               = "external-dns-pod-identity"
  assume_role_policy = data.aws_iam_policy_document.eks_assume_role.json
}

resource "aws_iam_policy" "external_dns_access" {
  name        = "AllowExternalDNSUpdates"
  description = "Allows ExternalDNS to update Route53"

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets",
          "route53:ListTagsForResources"
        ],
        "Resource" : [
          "arn:aws:route53:::hostedzone/*"
        ]
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "route53:ListHostedZones"
        ],
        "Resource" : [
          "*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "external_dns_route53" {
  role       = aws_iam_role.external_dns_pod_identity.name
  policy_arn = aws_iam_policy.external_dns_access.arn
}

# EKS Pod Identity for External DNS operator
# connects Service Account and EDO Namespace (even if not created yet)
resource "aws_eks_pod_identity_association" "external_dns_pod_identity" {
  cluster_name    = module.eks.cluster_name
  namespace       = "external-dns"
  service_account = "external-dns"
  role_arn        = aws_iam_role.external_dns_pod_identity.arn
}
