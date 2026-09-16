# GitLab CI job pods run untrusted code, such as builds for pull requests from forks. The Karpenter
# nodes that run them use this security group instead of the shared EKS node security group, so job
# pods can't reach pods on other nodes, or data stores (RDS, ElastiCache) that trust the node
# security group. Every packet a job pod sends leaves through its node's ENIs and carries this
# security group, including after kube-proxy translates a ClusterIP to a backend pod IP.
#
# The only paths from runner nodes into the rest of the cluster are the API server and CoreDNS; see
# the rules that reference this group in eks.tf.
resource "aws_security_group" "runner_nodes" {
  name        = "${local.eks_cluster_name}-runner-node-sg"
  description = "Karpenter nodes that run GitLab CI job pods"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "${local.eks_cluster_name}-runner-node-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "runner_nodes_all" {
  security_group_id = aws_security_group.runner_nodes.id
  description       = "All outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "runner_nodes_from_nodes" {
  security_group_id            = aws_security_group.runner_nodes.id
  description                  = "Cluster workloads to runner nodes, e.g. metrics scrapes"
  ip_protocol                  = "-1"
  referenced_security_group_id = module.eks.node_security_group_id
}

resource "aws_vpc_security_group_ingress_rule" "runner_nodes_kubelet_from_cluster" {
  security_group_id            = aws_security_group.runner_nodes.id
  description                  = "Cluster API to runner node kubelets, e.g. exec, attach, logs"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  referenced_security_group_id = module.eks.cluster_security_group_id
}
