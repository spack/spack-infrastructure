locals {
  cluster_name = "spack-${var.deployment_name}"
}

module "eks" {
  # https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest
  source  = "terraform-aws-modules/eks/aws"
  version = "19.5.1"

  cluster_name    = local.cluster_name
  cluster_version = var.kubernetes_version

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
      self        = true # Only apply this rule to other nodes in this security group
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

    windows = {
      instance_types        = ["m5.2xlarge"]
      create_security_group = false

      # Node pool size
      min_size     = 1
      max_size     = 1
      desired_size = 1

      # Prevent anything without a windows taint toleration from being scheduled on this node
      taints = {
        windows = {
          key    = "windows"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }

      # EC2 settings
      capacity_type = "ON_DEMAND"
      block_device_mappings = {
        sda1 = {
          device_name = "/dev/sda1"
          ebs = {
            volume_size           = 200
            volume_type           = "gp3"
            delete_on_termination = true
          }
        }
      }

      # Windows specific settings
      ami_type = "WINDOWS_FULL_2022_x86_64"
    }
  }

  cluster_addons = {
    aws-ebs-csi-driver = {
      addon_version            = "v1.20.0-eksbuild.1"
      service_account_role_arn = aws_iam_role.ebs_efs_csi_driver.arn
    }
  }
}

resource "aws_iam_role" "eks_cluster_access" {
  name = "SpackEKSClusterAccess-${var.deployment_name}"
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
            "arn:aws:iam::588562868276:user/tgamblin",
            "arn:aws:iam::588562868276:user/krattiger1",
            "arn:aws:iam::588562868276:user/mike",
            "arn:aws:iam::588562868276:user/alecscott",
            "arn:aws:iam::588562868276:user/zack",
            "arn:aws:iam::588562868276:user/joesnyder",
            "arn:aws:iam::588562868276:user/dan"
          ]
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
}


resource "aws_iam_role" "ebs_efs_csi_driver" {
  name = "EbsEfsDriverRole-${var.deployment_name}"
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:kube-system:ebs-csi-controller-sa",
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ebs_efs_csi_driver" {
  name = "EbsEfsDriverPolicy-${var.deployment_name}"
  role = aws_iam_role.ebs_efs_csi_driver.id
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateSnapshot",
          "ec2:AttachVolume",
          "ec2:DetachVolume",
          "ec2:ModifyVolume",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInstances",
          "ec2:DescribeSnapshots",
          "ec2:DescribeTags",
          "ec2:DescribeVolumes",
          "ec2:DescribeVolumesModifications"
        ],
        "Resource" : "*"
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateTags"
        ],
        "Resource" : [
          "arn:aws:ec2:*:*:volume/*",
          "arn:aws:ec2:*:*:snapshot/*"
        ],
        "Condition" : {
          "StringEquals" : {
            "ec2:CreateAction" : [
              "CreateVolume",
              "CreateSnapshot"
            ]
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteTags"
        ],
        "Resource" : [
          "arn:aws:ec2:*:*:volume/*",
          "arn:aws:ec2:*:*:snapshot/*"
        ]
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateVolume"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "aws:RequestTag/ebs.csi.aws.com/cluster" : "true"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:CreateVolume"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "aws:RequestTag/CSIVolumeName" : "*"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteVolume"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "ec2:ResourceTag/ebs.csi.aws.com/cluster" : "true"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteVolume"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "ec2:ResourceTag/CSIVolumeName" : "*"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteVolume"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "ec2:ResourceTag/kubernetes.io/created-for/pvc/name" : "*"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteSnapshot"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "ec2:ResourceTag/CSIVolumeSnapshotName" : "*"
          }
        }
      },
      {
        "Effect" : "Allow",
        "Action" : [
          "ec2:DeleteSnapshot"
        ],
        "Resource" : "*",
        "Condition" : {
          "StringLike" : {
            "ec2:ResourceTag/ebs.csi.aws.com/cluster" : "true"
          }
        }
      }
    ]
  })
}

# Define a configmap that provides the EKS Cluster name
resource "kubectl_manifest" "cluster_name_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
        name: cluster-info
        namespace: kube-system
    data:
        cluster-name: ${module.eks.cluster_name}
  YAML
}

# Define a configmap to enable windows
resource "kubectl_manifest" "windows_vpc_cni_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: amazon-vpc-cni
      namespace: kube-system
    data:
      enable-windows-ipam: "true"
  YAML
}
