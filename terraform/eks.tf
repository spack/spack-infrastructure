module "eks" {
  # https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest
  source  = "terraform-aws-modules/eks/aws"
  version = "19.5.1"

  cluster_name    = local.cluster_name
  cluster_version = "1.24"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Enables OIDC provider for cluster; required for Karpenter
  enable_irsa = true

  create_kms_key            = false
  cluster_encryption_config = {}

  cluster_endpoint_public_access = true

  manage_aws_auth_configmap = true
  aws_auth_roles = [
    {
      rolearn  = aws_iam_role.eks_cluster_access.arn
      username = "admin"
      groups   = ["system:masters"]
    },
  ]

  node_security_group_additional_rules = {
    ingress_self_all = {
      description = "Node to node all ports/protocols"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      type        = "ingress"
      self        = true
    }
  }

  node_security_group_tags = {
    # NOTE - if creating multiple security groups with this module, only tag the
    # security group that Karpenter should utilize with the following tag
    # (i.e. - at most, only one security group should have this tag in your account)
    "karpenter.sh/discovery" = local.cluster_name
  }

  # Only need one node to get Karpenter up and running.
  # This ensures core services such as VPC CNI, CoreDNS, etc. are up and running
  # so that Karpenter can be deployed and start managing compute capacity as required
  eks_managed_node_groups = {
    initial = {
      instance_types = ["m5.large"]
      # Not required nor used - avoid tagging two security groups with same tag as well
      create_security_group = false

      # Ensure enough capacity to run 2 Karpenter pods
      min_size     = 2
      max_size     = 3
      desired_size = 2
    }
  }
}

resource "aws_iam_role" "eks_cluster_access" {
  name_prefix = "SpackEKSClusterAccess"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : [
            "arn:aws:iam::588562868276:user/scott",
            "arn:aws:iam::588562868276:user/vsoch",
            "arn:aws:iam::588562868276:user/jacob",
            "arn:aws:iam::588562868276:user/chris",
            "arn:aws:iam::588562868276:user/tgamblin",
            "arn:aws:iam::588562868276:user/krattiger1",
            "arn:aws:iam::588562868276:user/mike",
            "arn:aws:iam::588562868276:user/alecscott",
            "arn:aws:iam::588562868276:user/zack",
            "arn:aws:iam::588562868276:user/joesnyder"
          ]
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
}
