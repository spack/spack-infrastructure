# Dedicated security group for CI runner nodes.
#
# Runner nodes execute arbitrary user-submitted pipeline code and, prior to this
# change, shared the same security group as every other node in the cluster
# (module.eks.node_security_group_id) -- including network-level access to the
# GitLab Redis instance (see gitlab_redis.tf), which has no AUTH configured.
# CI jobs have no legitimate need to reach Redis; giving runner nodes their own
# security group (excluded from gitlab_redis.tf's security_group_ids) removes
# that path without touching the broad internet egress CI jobs actually need
# (package/source mirrors are effectively unbounded and can't be allow-listed).
resource "aws_security_group" "runner_nodes" {
  name        = "${local.eks_cluster_name}-runner-node-sg"
  description = "Security group for Karpenter-provisioned CI runner nodes, isolated from the shared node SG"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name                     = "${local.eks_cluster_name}-runner-node-sg"
    "karpenter.sh/discovery" = "${local.eks_cluster_name}-runners"
  }
}

# CI jobs fetch source tarballs/patches from hundreds of distinct, constantly
# changing hosts (package mirrors, forges, etc.) -- a default-deny egress
# allow-list isn't practical here, so egress stays fully open, matching the
# existing shared node SG's behavior.
resource "aws_vpc_security_group_egress_rule" "runner_nodes_all" {
  security_group_id = aws_security_group.runner_nodes.id
  description       = "Allow all egress"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# There is intentionally no self-referencing rule. Nothing on one runner node
# needs to connect to another (CoreDNS runs on the shared node SG, and traffic
# between pods on the same node never passes through a security group), and
# omitting it keeps CI job pods on different runner nodes from reaching each
# other.

# Cluster workloads on the shared node SG need to reach runner nodes: Prometheus
# scrapes each node's kubelet (cAdvisor) and node exporter directly, and the
# analytics job processor reads CI job CPU/memory usage from those metrics.
# metrics-server also scrapes kubelets. This only allows connections *into*
# runner nodes; it doesn't let runner pods reach anything on the shared node SG.
resource "aws_vpc_security_group_ingress_rule" "runner_nodes_from_shared_nodes" {
  security_group_id            = aws_security_group.runner_nodes.id
  description                  = "Shared node SG to runner nodes, e.g. metrics scrapes"
  ip_protocol                  = "-1"
  referenced_security_group_id = module.eks.node_security_group_id
}

# The EKS control plane needs to reach kubelet/webhook ports on every node it
# manages, regardless of which security group that node carries. These mirror
# the equivalent rules the terraform-aws-modules/eks module auto-generates for
# the shared node security group -- verify against `terraform plan` /
# `aws ec2 describe-security-groups` on the existing node SG if this drifts
# from what the module actually creates on your provider version.
locals {
  runner_node_cluster_ports = {
    kubelet       = 10250
    https         = 443
    webhook_6443  = 6443
    webhook_8443  = 8443
    webhook_9443  = 9443
    webhook_4443  = 4443
    webhook_10251 = 10251
  }
}

resource "aws_vpc_security_group_ingress_rule" "runner_nodes_cluster_api" {
  for_each = local.runner_node_cluster_ports

  security_group_id            = aws_security_group.runner_nodes.id
  description                  = "Cluster API to node ${each.value}/tcp (${each.key})"
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  referenced_security_group_id = module.eks.cluster_security_group_id
}

# Rules that let runner nodes reach the rest of the cluster (the API server and
# CoreDNS) live on the shared security groups, in eks.tf.
