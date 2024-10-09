terraform {
  required_version = "~> 1.9.5"

  backend "s3" {
    bucket         = "spack-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "spack-terraform-state-locks"
    encrypt        = true
  }
}
