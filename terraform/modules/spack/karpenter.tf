module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "18.31.0"

  cluster_name = module.eks.cluster_name

  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["karpenter:karpenter"]

  # Since Karpenter is running on an EKS Managed Node group,
  # we can re-use the role that was created for the node group
  create_iam_role = false
  iam_role_arn    = module.eks.eks_managed_node_groups["initial"].iam_role_arn
}

resource "helm_release" "karpenter" {
  namespace        = "karpenter"
  create_namespace = true

  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = "v0.20.0"

  set {
    name  = "settings.aws.clusterName"
    value = module.eks.cluster_name
  }

  set {
    name  = "settings.aws.clusterEndpoint"
    value = module.eks.cluster_endpoint
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.karpenter.irsa_arn
  }

  set {
    name  = "settings.aws.defaultInstanceProfile"
    value = module.karpenter.instance_profile_name
  }

  set {
    name  = "settings.aws.interruptionQueueName"
    value = module.karpenter.queue_name
  }
}


resource "kubectl_manifest" "karpenter_provisioner" {
  yaml_body = <<-YAML
    apiVersion: karpenter.sh/v1alpha5
    kind: Provisioner
    metadata:
      name: default
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
      limits:
        resources:
          cpu: 1000
      providerRef:
        name: default
      ttlSecondsAfterEmpty: 30
  YAML

  depends_on = [
    helm_release.karpenter
  ]
}

resource "kubectl_manifest" "karpenter_node_template" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1alpha1
    kind: AWSNodeTemplate
    metadata:
      name: default
    spec:
      subnetSelector:
        # This value *must* match one of the tags placed on the subnets for this
        # EKS cluster (see vpc.tf for these).
        # We use the "deployment_name" variable here instead of the full cluster name
        # because the full cluster name isn't available at the time that we bootstrap
        # the VPC resources (including subnets). However, "deployment_name" is also
        # a unique-per-cluster value, so it should work just as well.
        karpenter.sh/discovery: ${var.deployment_name}
      securityGroupSelector:
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

resource "kubectl_manifest" "karpenter_pcluster_node_template" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1alpha1
    kind: AWSNodeTemplate
    metadata:
      name: pcluster-amzn2-arm64
    spec:
      amiSelector:
        # aws-parallelcluster-3.5.1-amzn2-hvm-arm64-202303171148 2023-03-17T11-52-32.544Z
        "aws::ids": "ami-0d87b43677ef96ab9"
      subnetSelector:
        # This value *must* match one of the tags placed on the subnets for this
        # EKS cluster (see vpc.tf for these).
        # We use the "deployment_name" variable here instead of the full cluster name
        # because the full cluster name isn't available at the time that we bootstrap
        # the VPC resources (including subnets). However, "deployment_name" is also
        # a unique-per-cluster value, so it should work just as well.
        karpenter.sh/discovery: ${var.deployment_name}
      securityGroupSelector:
        karpenter.sh/discovery: ${module.eks.cluster_name}
      tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
        spack.io/pcluster: "true"
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
