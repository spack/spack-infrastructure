locals {
  cluster_name = "spack-${var.deployment_name}"
}

# module.staging_cluster.module.eks.aws_cloudwatch_log_group.this[0]:
resource "aws_cloudwatch_log_group" "this" {
  id                = "/aws/eks/${local.cluster_name}/cluster"
  name              = "/aws/eks/${local.cluster_name}/cluster"
  retention_in_days = 90
}

# module.staging_cluster.module.eks.aws_eks_addon.this["aws-ebs-csi-driver"]:
resource "aws_eks_addon" "this" {
  addon_name               = "aws-ebs-csi-driver"
  addon_version            = "v1.20.0-eksbuild.1"
  cluster_name             = aws_eks_cluster.this.name
  service_account_role_arn = aws_iam_role.ebs_efs_csi_driver.arn
}

# module.staging_cluster.module.eks.aws_eks_cluster.this[0]:
resource "aws_eks_cluster" "this" {
  name     = local.cluster_name
  role_arn = aws_iam_role.cluster_role.arn
  version  = "1.27"

  enabled_cluster_log_types = [
    "api",
    "audit",
    "authenticator",
  ]

  vpc_config {
    security_group_ids = [
      aws_security_group.cluster.id,
    ]
    subnet_ids              = module.vpc.private_subnets
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs = [
      "0.0.0.0/0",
    ]
  }
}

data "tls_certificate" "cluster_oidc" {
  url = aws_eks_cluster.this[0].identity[0].oidc[0].issuer
}

# module.staging_cluster.module.eks.aws_iam_openid_connect_provider.oidc_provider[0]:
resource "aws_iam_openid_connect_provider" "oidc_provider" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = data.tls_certificate.cluster_oidc[0].certificates[*].sha1_fingerprint
  url             = aws_eks_cluster.this[0].identity[0].oidc[0].issuer
  tags = {
    Name = "${aws_eks_cluster.this.name}-eks-irsa"
  }
}

# module.staging_cluster.module.eks.aws_iam_role.this[0]:
resource "aws_iam_role" "cluster_role" {
  arn = "arn:aws:iam::588562868276:role/spack-staging-cluster-20230510190122143900000004"
  assume_role_policy = jsonencode(
    {
      Statement = [
        {
          Action = "sts:AssumeRole"
          Effect = "Allow"
          Principal = {
            Service = "eks.amazonaws.com"
          }
          Sid = "EKSClusterAssumeRole"
        },
      ]
      Version = "2012-10-17"
    }
  )
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController",
  ]
  name_prefix = "${local.cluster_name}-cluster-"

  inline_policy {
    name = "${local.cluster_name}-cluster"
    policy = jsonencode(
      {
        Statement = [
          {
            Action = [
              "logs:CreateLogGroup",
            ]
            Effect   = "Deny"
            Resource = "*"
          },
        ]
        Version = "2012-10-17"
      }
    )
  }
}

# module.staging_cluster.module.eks.aws_iam_role_policy_attachment.this["AmazonEKSClusterPolicy"]:
resource "aws_iam_role_policy_attachment" "this" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster_role.name
}

# module.staging_cluster.module.eks.aws_iam_role_policy_attachment.this["AmazonEKSVPCResourceController"]:
resource "aws_iam_role_policy_attachment" "this" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.cluster_role.name
}

# module.staging_cluster.module.eks.aws_security_group.cluster[0]:
resource "aws_security_group" "cluster" {
  arn         = "arn:aws:ec2:us-west-2:588562868276:security-group/sg-014917862b730ba6c"
  description = "EKS cluster security group"
  egress      = []
  ingress = [
    {
      cidr_blocks      = []
      description      = "Node groups to cluster API"
      from_port        = 443
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups = [
        aws_security_group.node.id,
      ]
      self    = false
      to_port = 443
    },
  ]
  #   name                   = "spack-staging-cluster-20230510190122143200000001"
  name_prefix = "${local.cluster_name}-cluster-"
  #   owner_id               = "588562868276"
  #   revoke_rules_on_delete = false
  tags = {
    "Name" = "${local.cluster_name}-cluster"
  }
  #   vpc_id = "vpc-072e79b2091d1a12a"
  vpc_id = module.vpc.vpc_id
}

# module.staging_cluster.module.eks.aws_security_group.node[0]:
resource "aws_security_group" "node" {
  description = "EKS node shared security group"
  egress = [
    {
      cidr_blocks = [
        "0.0.0.0/0",
      ]
      description      = "Allow all egress"
      from_port        = 0
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "-1"
      security_groups  = []
      self             = false
      to_port          = 0
    },
  ]
  ingress = [
    {
      cidr_blocks = [
        "0.0.0.0/0",
      ]
      from_port        = 6379
      protocol         = "tcp"
      self             = false
      to_port          = 6379
    },
    {
      from_port        = 0
      protocol         = "-1"
      security_groups = [
        "sg-07375a99d12100919",
      ]
      self    = false
      to_port = 0
    },
    {
      description      = ""
      from_port        = 0
      protocol         = "-1"
      security_groups = [
        "sg-0e6e8ab42074f9981",
      ]
      self    = false
      to_port = 0
    },
    {
      description      = "Cluster API to node 4443/tcp webhook"
      from_port        = 4443
      protocol         = "tcp"
      security_groups = [
        aws_security_group.cluster.id,
      ]
      self    = false
      to_port = 4443
    },
    {
      cidr_blocks      = []
      description      = "Cluster API to node 8443/tcp webhook"
      from_port        = 8443
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups = [
        aws_security_group.cluster.id,
      ]
      self    = false
      to_port = 8443
    },
    {
      cidr_blocks      = []
      description      = "Cluster API to node 9443/tcp webhook"
      from_port        = 9443
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups = [
        aws_security_group.cluster.id,
      ]
      self    = false
      to_port = 9443
    },
    {
      cidr_blocks      = []
      description      = "Cluster API to node groups"
      from_port        = 443
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups = [
        aws_security_group.cluster.id,
      ]
      self    = false
      to_port = 443
    },
    {
      cidr_blocks      = []
      description      = "Cluster API to node kubelets"
      from_port        = 10250
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups = [
        aws_security_group.cluster.id,
      ]
      self    = false
      to_port = 10250
    },
    {
      cidr_blocks      = []
      description      = "Node to node CoreDNS UDP"
      from_port        = 53
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "udp"
      security_groups  = []
      self             = true
      to_port          = 53
    },
    {
      cidr_blocks      = []
      description      = "Node to node CoreDNS"
      from_port        = 53
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups  = []
      self             = true
      to_port          = 53
    },
    {
      cidr_blocks      = []
      description      = "Node to node all ports/protocols"
      from_port        = 0
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "-1"
      security_groups  = []
      self             = true
      to_port          = 0
    },
    {
      cidr_blocks      = []
      description      = "Node to node ingress on ephemeral ports"
      from_port        = 1025
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      protocol         = "tcp"
      security_groups  = []
      self             = true
      to_port          = 65535
    },
  ]
  name                   = "spack-staging-node-20230510190122143800000003"
  name_prefix            = "spack-staging-node-"
  owner_id               = "588562868276"
  revoke_rules_on_delete = false
  tags = {
    "Name"                                = "spack-staging-node"
    "karpenter.sh/discovery"              = "spack-staging"
    "kubernetes.io/cluster/spack-staging" = "owned"
  }
  tags_all = {
    "Name"                                = "spack-staging-node"
    "karpenter.sh/discovery"              = "spack-staging"
    "kubernetes.io/cluster/spack-staging" = "owned"
  }
  vpc_id = "vpc-072e79b2091d1a12a"
}

# module.staging_cluster.module.eks.aws_security_group_rule.cluster["ingress_nodes_443"]:
resource "aws_security_group_rule" "cluster" {
  description              = "Node groups to cluster API"
  from_port                = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.cluster.id
  self                     = false
  source_security_group_id = aws_security_group.node.id
  to_port                  = 443
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["egress_all"]:
resource "aws_security_group_rule" "node" {
  cidr_blocks = [
    "0.0.0.0/0",
  ]
  description            = "Allow all egress"
  from_port              = 0
  protocol               = "-1"
  security_group_id      = aws_security_group.node.id
  self                   = false
  to_port                = 0
  type                   = "egress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_cluster_443"]:
resource "aws_security_group_rule" "node" {
  description              = "Cluster API to node groups"
  from_port                = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.node.id
  self                     = false
  source_security_group_id = aws_security_group.cluster.id
  to_port                  = 443
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_cluster_4443_webhook"]:
resource "aws_security_group_rule" "node" {
  description              = "Cluster API to node 4443/tcp webhook"
  from_port                = 4443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.node.id
  self                     = false
  source_security_group_id = aws_security_group.cluster.id
  to_port                  = 4443
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_cluster_8443_webhook"]:
resource "aws_security_group_rule" "node" {
  description              = "Cluster API to node 8443/tcp webhook"
  from_port                = 8443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.node.id
  self                     = false
  source_security_group_id = aws_security_group.cluster.id
  to_port                  = 8443
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_cluster_9443_webhook"]:
resource "aws_security_group_rule" "node" {
  description              = "Cluster API to node 9443/tcp webhook"
  from_port                = 9443
  id                       = "sgrule-1329936648"
  prefix_list_ids          = []
  protocol                 = "tcp"
  security_group_id        = aws_security_group.node.id
  security_group_rule_id   = "sgr-0de0a0345a1ccfb09"
  self                     = false
  source_security_group_id = aws_security_group.cluster.id
  to_port                  = 9443
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_cluster_kubelet"]:
resource "aws_security_group_rule" "node" {
  description              = "Cluster API to node kubelets"
  from_port                = 10250
  protocol                 = "tcp"
  security_group_id        = aws_security_group.node.id
  self                     = false
  source_security_group_id = aws_security_group.cluster.id
  to_port                  = 10250
  type                     = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_nodes_ephemeral"]:
resource "aws_security_group_rule" "node" {
  description            = "Node to node ingress on ephemeral ports"
  from_port              = 1025
  protocol               = "tcp"
  security_group_id      = aws_security_group.node.id
  self                   = true
  to_port                = 65535
  type                   = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_self_all"]:
resource "aws_security_group_rule" "node" {
  description            = "Node to node all ports/protocols"
  from_port              = 0
  prefix_list_ids        = []
  protocol               = "-1"
  security_group_id      = aws_security_group.node.id
  self                   = true
  to_port                = 0
  type                   = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_self_coredns_tcp"]:
resource "aws_security_group_rule" "node" {
  description            = "Node to node CoreDNS"
  from_port              = 53
  protocol               = "tcp"
  security_group_id      = aws_security_group.node.id
  self                   = true
  to_port                = 53
  type                   = "ingress"
}

# module.staging_cluster.module.eks.aws_security_group_rule.node["ingress_self_coredns_udp"]:
resource "aws_security_group_rule" "node" {
  description            = "Node to node CoreDNS UDP"
  from_port              = 53
  protocol               = "udp"
  security_group_id      = aws_security_group.node.id
  self                   = true
  to_port                = 53
  type                   = "ingress"
}

# module.staging_cluster.module.eks.kubernetes_config_map_v1_data.aws_auth[0]:
resource "kubernetes_config_map_v1_data" "aws_auth" {
  data = {
    "mapAccounts" = jsonencode([])
    "mapRoles"    = <<-EOT
            - "groups":
              - "system:bootstrappers"
              - "system:nodes"
              "rolearn": "arn:aws:iam::588562868276:role/initial-eks-node-group-20230510190122143200000002"
              "username": "system:node:{{EC2PrivateDNSName}}"
            - "groups":
              - "eks:kube-proxy-windows"
              - "system:bootstrappers"
              - "system:nodes"
              "rolearn": "arn:aws:iam::588562868276:role/initial-eks-node-group-20230510190122143200000002"
              "username": "system:node:{{EC2PrivateDNSName}}"
            - "groups":
              - "system:masters"
              "rolearn": "arn:aws:iam::588562868276:role/SpackEKSClusterAccess-staging"
              "username": "admin"
            - "groups":
              - "github-actions"
              "rolearn": "arn:aws:iam::588562868276:role/GitHubActionsReadonlyRole-staging"
              "username": "github-actions"
        EOT
    "mapUsers"    = jsonencode([])
  }
  field_manager = "Terraform"
  force         = true
  id            = "kube-system/aws-auth"

  metadata {
    name      = "aws-auth"
    namespace = "kube-system"
  }
}


# module.staging_cluster.module.eks.module.eks_managed_node_group["initial"].data.aws_caller_identity.current:
data "aws_caller_identity" "current" {
  account_id = "588562868276"
  arn        = "arn:aws:iam::588562868276:user/mike"
  id         = "588562868276"
  user_id    = "AIDAYSCIUVA2A4X4AD44G"
}

# module.staging_cluster.module.eks.module.eks_managed_node_group["initial"].data.aws_partition.current:
data "aws_partition" "current" {
  dns_suffix         = "amazonaws.com"
  id                 = "aws"
  partition          = "aws"
  reverse_dns_prefix = "com.amazonaws"
}

# module.staging_cluster.module.eks.module.eks_managed_node_group["initial"].aws_eks_node_group.this[0]:
resource "aws_eks_node_group" "this" {
  ami_type      = "AL2_x86_64"
#   arn           = "arn:aws:eks:us-west-2:588562868276:nodegroup/spack-staging/initial-2023051019114386330000000c/c4c40389-caae-d446-0d20-76444f7855ce"
  capacity_type = "ON_DEMAND"
  cluster_name  = aws_eks_cluster.this.id
#   id            = "spack-staging:initial-2023051019114386330000000c"
  instance_types = [
    "m5.large",
  ]
  labels                 = {}
  node_group_name_prefix = "initial-"
  node_role_arn          = aws_iam_role.managed_node_group.arn
  release_version        = "1.27.3-20230728"
#   resources = [
#     {
#       autoscaling_groups = [
#         {
#           name = "eks-initial-2023051019114386330000000c-c4c40389-caae-d446-0d20-76444f7855ce"
#         },
#       ]
#       remote_access_security_group_id = ""
#     },
#   ]
  subnet_ids = [
    "subnet-0883aaae25fb98c4b",
    "subnet-097b7f0da795d24ca",
    "subnet-0cd8e27557c0fbb8b",
    "subnet-0d936c0c21791033c",
  ]
  tags = {
    "Name" = "initial"
  }
  tags_all = {
    "Name" = "initial"
  }
  version = "1.27"

  launch_template {
    id      = "lt-0457e2b8578895ab9"
    name    = "initial-2023051019114304730000000a"
    version = "1"
  }

  scaling_config {
    desired_size = 2
    max_size     = 3
    min_size     = 2
  }

  timeouts {}

  update_config {
    max_unavailable            = 0
    max_unavailable_percentage = 33
  }
}

# module.staging_cluster.module.eks.module.eks_managed_node_group["initial"].aws_launch_template.this[0]:
resource "aws_launch_template" "this" {
  arn                     = "arn:aws:ec2:us-west-2:588562868276:launch-template/lt-0457e2b8578895ab9"
  default_version         = 1
  description             = "Custom launch template for initial EKS managed node group"
  disable_api_stop        = false
  disable_api_termination = false
#   id                      = "lt-0457e2b8578895ab9"
#   latest_version          = 1
  name                    = "initial-2023051019114304730000000a"
  name_prefix             = "initial-"
  security_group_names    = []
  tags                    = {}
  tags_all                = {}
  update_default_version  = true
  vpc_security_group_ids = [
    aws_security_group.node.id,
  ]

  metadata_options {
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
    http_put_response_hop_limit = 2
    http_tokens                 = "required"
    instance_metadata_tags      = "disabled"
  }

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      "Name" = "initial"
    }
  }
  tag_specifications {
    resource_type = "network-interface"
    tags = {
      "Name" = "initial"
    }
  }
  tag_specifications {
    resource_type = "volume"
    tags = {
      "Name" = "initial"
    }
  }
}


# module.staging_cluster.module.eks.module.kms.data.aws_partition.current:
data "aws_partition" "current" {
  dns_suffix         = "amazonaws.com"
  id                 = "aws"
  partition          = "aws"
  reverse_dns_prefix = "com.amazonaws"
}
