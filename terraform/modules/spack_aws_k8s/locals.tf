locals {
  suffix = "${var.deployment_name != "prod" ? "-${var.deployment_name}" : ""}-${var.deployment_stage}"
}

locals {
  eks_cluster_name = "spack${local.suffix}"
}
