terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data source that allows us to dynamically determine the current AWS region
data "aws_region" "current" {}

# Data source that allows us to dynamically determine id of the current "canonical user"
data "aws_canonical_user_id" "current" {}
