data "aws_eks_cluster" "spack" {
  name = "spack${local.suffix}-${var.deployment_stage}"
}

data "aws_iam_openid_connect_provider" "spack" {
  url = data.aws_eks_cluster.spack.identity[0].oidc[0].issuer
}

data "aws_vpc" "spack" {
  id = data.aws_eks_cluster.spack.vpc_config[0].vpc_id
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.spack.id]
  }
  filter {
    name   = "tag:kubernetes.io/role/elb"
    values = ["1"]
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.spack.id]
  }
  filter {
    name   = "tag:kubernetes.io/role/internal-elb"
    values = ["1"]
  }
}

data "aws_subnet" "spack" {
  for_each = toset(concat(data.aws_subnets.public.ids, data.aws_subnets.private.ids))
  id       = each.value
}

data "aws_route53_zone" "spack_io" {
  name         = "spack.io"
  private_zone = false
}

data "aws_elasticache_replication_group" "spackbot_queue" {
  replication_group_id = "pr-binary-graduation-queue-${var.deployment_name}-${var.deployment_stage}"
}

data "aws_iam_role" "eks_cluster_access" {
  name = "SpackEKSClusterAccess-${var.deployment_name}-${var.deployment_stage}"
}
