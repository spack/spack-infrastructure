locals {
  suffix             = "${var.deployment_name != "prod" ? "-${var.deployment_name}" : ""}-${var.deployment_stage}"
  domain_suffix      = var.deployment_name == "prod" ? "" : "${var.deployment_name}."
  bucket_name_suffix = var.deployment_name == "prod" ? "" : "-${var.deployment_name}"
}

locals {
  eks_cluster_name = "spack${local.suffix}"
}
