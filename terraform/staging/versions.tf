terraform {
  required_version = "~> 1.11.3"

  backend "s3" {
    bucket       = "spack-terraform-state"
    key          = "staging/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
