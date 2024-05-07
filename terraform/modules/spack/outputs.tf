output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_ca_certificate" {
  value = base64decode(module.eks.cluster_certificate_authority_data)
}

output "cluster_access_role_arn" {
  value = aws_iam_role.eks_cluster_access.arn
}

output "oidc_provider" {
  value = module.eks.oidc_provider
}

output "oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "protected_binary_bucket_arn" {
  value = module.protected_binary_mirror.bucket_arn
}

output "pr_binary_bucket_arn" {
  value = module.pr_binary_mirror.bucket_arn
}
