resource "aws_elasticache_subnet_group" "gitlab" {
  name       = "spack-gitlab${local.suffix}"
  subnet_ids = concat(module.vpc.private_subnets, module.vpc.public_subnets)
}

resource "aws_elasticache_replication_group" "gitlab" {
  replication_group_id = "spack-gitlab${local.suffix}"
  description          = "Managed by Terraform. Redis instance for GitLab."

  node_type = var.gitlab_redis_instance_class

  subnet_group_name = aws_elasticache_subnet_group.gitlab.name

  port                       = 6379
  apply_immediately          = true
  auto_minor_version_upgrade = false

  automatic_failover_enabled = true
  multi_az_enabled           = true

  # Ensure there's a cache cluster in each AZ
  preferred_cache_cluster_azs = local.azs
  num_cache_clusters          = length(local.azs)

  # Allow EKS nodes to access redis
  security_group_ids = [module.eks.node_security_group_id]

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.gitlab_elasticache_slow.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.gitlab_elasticache_engine.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "engine-log"
  }
}

resource "aws_cloudwatch_log_group" "gitlab_elasticache_slow" {
  name              = "spack-gitlab${local.suffix}-elasticache-slow"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "gitlab_elasticache_engine" {
  name              = "spack-gitlab${local.suffix}-elasticache-engine"
  retention_in_days = 7
}

# AWS secrets for Redis
resource "kubectl_manifest" "gitlab_redis_config" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gitlab-elasticache-config
      namespace: ${kubectl_manifest.gitlab_namespace.name}
    data:
      values.yaml: |
        global:
          redis:
            host: ${aws_elasticache_replication_group.gitlab.primary_endpoint_address}
            auth:
              enabled: false
  YAML
}
