locals {
  karpenter_chart_version = "1.8.1"
}

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "21.8.0"

  cluster_name = module.eks.cluster_name

  # Name needs to match role name passed to the EC2NodeClass
  node_iam_role_use_name_prefix   = false
  node_iam_role_name              = "KarpenterControllerNodeRole-${var.deployment_name}-${var.deployment_stage}"
  create_pod_identity_association = true

  iam_role_policies = {
    # Attach role that allows Karpenter to create instance profiles for Windows nodes.
    # See comment above the aws_iam_policy resource below for more details.
    "karpenter-windows-pass-role" = aws_iam_policy.karpenter_windows_pass_role.arn
  }
}


resource "helm_release" "karpenter_crds" {
  namespace        = "kube-system"
  create_namespace = true

  name       = "karpenter-crd"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter-crd"
  version    = local.karpenter_chart_version
}

resource "helm_release" "karpenter" {
  name      = "karpenter"
  namespace = "kube-system"

  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = local.karpenter_chart_version

  values = [
    <<-EOT
    nodeSelector:
      karpenter.sh/controller: 'true'
    tolerations:
      - key: CriticalAddonsOnly
        operator: Exists
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
    serviceMonitor:
      enabled: true
    EOT
  ]

  depends_on = [helm_release.karpenter_crds]
}

resource "kubectl_manifest" "karpenter_node_class" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1
    kind: EC2NodeClass
    metadata:
      name: default
    spec:
      amiFamily: AL2023
      amiSelectorTerms:
        - alias: al2023@latest
      userData: |
        apiVersion: node.eks.aws/v1alpha1
        kind: NodeConfig
        spec:
          kubelet:
            config:
              # The Amazon Linux 2023 AMI overrides the default kubelet config to disable
              # serializeImagePulls in order to improve performance.
              # This is not ideal for our use case, where we frequently create many pods at once
              # when start a CI pipeline, because it can cause us to hit the container registry's
              # max QPS, so we override it here.
              serializeImagePulls: true
      role: ${module.karpenter.node_iam_role_name}
      subnetSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${module.eks.cluster_name}
      securityGroupSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${module.eks.cluster_name}
      tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
      blockDeviceMappings:
        - deviceName: /dev/xvda
          ebs:
            volumeSize: 200Gi
            volumeType: gp3
            deleteOnTermination: true
  YAML

  depends_on = [
    helm_release.karpenter
  ]
}

resource "kubectl_manifest" "karpenter_windows_node_class" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1
    kind: EC2NodeClass
    metadata:
      name: windows
    spec:
      amiFamily: Windows2022
      amiSelectorTerms:
        - alias: windows2022@latest
      role: ${module.karpenter_windows.node_iam_role_name}
      subnetSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${module.eks.cluster_name}
      securityGroupSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${module.eks.cluster_name}
      tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
      blockDeviceMappings:
        - deviceName: /dev/sda1
          ebs:
            volumeSize: 200Gi
            volumeType: gp3
            deleteOnTermination: true
  YAML

  depends_on = [
    helm_release.karpenter
  ]
}

module "karpenter_windows" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "21.8.0"

  cluster_name = module.eks.cluster_name

  create_node_iam_role          = true
  node_iam_role_use_name_prefix = false
  node_iam_role_name            = "KarpenterWindowsControllerNodeRole-${var.deployment_name}-${var.deployment_stage}"
  create_access_entry           = true
  access_entry_type             = "EC2_WINDOWS"

  create_pod_identity_association = true
  enable_spot_termination         = false
  create_instance_profile         = false
  create_iam_role                 = false # we'll use the role created by the `karpenter` module above
}

resource "aws_iam_policy" "karpenter_windows_pass_role" {
  # This policy allows the Karpenter controller role to dynamically create instance profiles for
  # Windows nodes. This is necessary because we have two instances of the Karpenter TF module -
  # one for Linux nodes and one for Windows nodes. The Linux nodes module creates the controller
  # role, so we reuse that role for the Windows module. The Windows module does *not* attach this
  # policy to the controller role for us, so we need to do it here.
  #
  # The only place I could find documentation on this is the brief reference to the iam:PassRole
  # action in the Karpenter CloudFormation deploy docs - https://karpenter.sh/v1.0/reference/cloudformation/#karpenternoderole
  name        = "KarpenterInstanceProfilePolicyWindows-${var.deployment_name}-${var.deployment_stage}"
  description = "Policy for Karpenter controller node role"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Action" : "iam:PassRole",
        "Condition" : {
          "StringEquals" : {
            "iam:PassedToService" : "ec2.amazonaws.com"
          }
        },
        "Effect" : "Allow",
        "Resource" : module.karpenter_windows.node_iam_role_arn
      }
    ]
  })
}
