terraform {
  required_version = "~> 1.11.3"

  backend "s3" {
    bucket         = "spack-terraform-state"
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "spack-terraform-state-locks"
    encrypt        = true
  }
}
