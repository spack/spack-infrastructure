output "nat_public_ips" {
  value = module.vpc.nat_public_ips
}

output "pr_binary_mirror_bucket_name" {
  value = module.pr_binary_mirror.bucket_name
}

output "protected_binary_mirror_bucket_name" {
  value = module.protected_binary_mirror.bucket_name
}

output "protected_binary_cache_read_only_policy_arn" {
  description = "ARN of the managed policy granting read+list on the protected binary mirror."
  value       = aws_iam_policy.protected_binary_cache_read_only.arn
}

output "pr_binary_cache_read_only_policy_arn" {
  description = "ARN of the managed policy granting read+list on the PR binary mirror."
  value       = aws_iam_policy.pr_binary_cache_read_only.arn
}

output "binary_cache_full_access_policy_arn" {
  description = "ARN of the managed policy granting full object access on both binary mirrors."
  value       = aws_iam_policy.binary_cache_full_access.arn
}
