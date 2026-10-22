output "nat_public_ips" {
  value = module.vpc.nat_public_ips
}

output "pr_binary_mirror_bucket_name" {
  value = module.pr_binary_mirror.bucket_name
}

output "protected_binary_mirror_bucket_name" {
  value = module.protected_binary_mirror.bucket_name
}
