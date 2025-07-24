resource "aws_elasticache_subnet_group" "pr_binary_graduation_task_queue" {
  name       = "pr-binary-graduation-queue-${var.deployment_name}-${var.deployment_stage}"
  subnet_ids = concat(module.vpc.private_subnets, module.vpc.public_subnets)
}

resource "aws_elasticache_replication_group" "pr_binary_graduation_task_queue" {
  replication_group_id = "pr-binary-graduation-queue-${var.deployment_name}-${var.deployment_stage}"
  description          = "Used by python RQ module to store pending tasks for workers"

  engine               = "redis"
  engine_version       = "7.0"
  node_type            = "cache.t3.small"
  port                 = 6379
  parameter_group_name = "default.redis7"

  snapshot_retention_limit = 1
  snapshot_window          = "08:30-09:30"

  subnet_group_name          = aws_elasticache_subnet_group.pr_binary_graduation_task_queue.name
  automatic_failover_enabled = true

  replicas_per_node_group = 1
  num_node_groups         = 1

  security_group_ids = [module.eks.node_security_group_id]
}
