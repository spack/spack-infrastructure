locals {
  karpenter_version = "v0.34.0"
}

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "20.17.2"

  cluster_name = module.eks.cluster_name

  enable_pod_identity             = true
  create_pod_identity_association = true

  enable_irsa                     = true
  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["karpenter:karpenter"]

  # # Used to attach additional IAM policies to the Karpenter node IAM role
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}

resource "helm_release" "karpenter" {
  namespace        = "karpenter"
  create_namespace = false

  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = local.karpenter_version

  values = [
    <<-EOT
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueueName: ${module.karpenter.queue_name}
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.karpenter.iam_role_arn}
    controller:
      resources:
        requests:
          cpu: 1
          memory: 1Gi
        limits:
          cpu: 1
          memory: 1Gi
    tolerations:
      - key: CriticalAddonsOnly
    serviceMonitor:
      enabled: true
    EOT
  ]

  depends_on = [
    helm_release.karpenter_crds
  ]
}

resource "helm_release" "karpenter_crds" {
  namespace        = "karpenter"
  create_namespace = true

  name       = "karpenter-crd"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter-crd"
  version    = local.karpenter_version
}

resource "kubectl_manifest" "karpenter_provisioner" {
  yaml_body = <<-YAML
    apiVersion: karpenter.sh/v1beta1
    kind: NodePool
    metadata:
      name: default
    spec:
      template:
        spec:
          requirements:
            - key: karpenter.sh/capacity-type
              operator: In
              values: ["spot"]
          nodeClassRef:
            apiVersion: karpenter.k8s.aws/v1beta1
            kind: EC2NodeClass
            name: default
      limits:
        cpu: 1000
      disruption:
        consolidationPolicy: WhenEmpty
        consolidateAfter: 30s
  YAML

  depends_on = [
    helm_release.karpenter
  ]
}

resource "kubectl_manifest" "karpenter_node_template" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1beta1
    kind: EC2NodeClass
    metadata:
      name: default
    spec:
      amiFamily: AL2
      role: ${module.karpenter.node_iam_role_name}
      subnetSelectorTerms:
        # This value *must* match one of the tags placed on the subnets for this
        # EKS cluster (see vpc.tf for these).
        # We use the "deployment_name" variable here instead of the full cluster name
        # because the full cluster name isn't available at the time that we bootstrap
        # the VPC resources (including subnets). However, "deployment_name" is also
        # a unique-per-cluster value, so it should work just as well.
        - tags:
            karpenter.sh/discovery: ${var.deployment_name}
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

resource "kubectl_manifest" "windows_node_template" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1beta1
    kind: EC2NodeClass
    metadata:
      name: windows
    spec:
      role: ${module.karpenter.node_iam_role_name}
      subnetSelectorTerms:
        # This value *must* match one of the tags placed on the subnets for this
        # EKS cluster (see vpc.tf for these).
        # We use the "deployment_name" variable here instead of the full cluster name
        # because the full cluster name isn't available at the time that we bootstrap
        # the VPC resources (including subnets). However, "deployment_name" is also
        # a unique-per-cluster value, so it should work just as well.
        - tags:
            karpenter.sh/discovery: ${var.deployment_name}
      securityGroupSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${module.eks.cluster_name}
      tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
      amiFamily: Windows2022
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
