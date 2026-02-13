# Terraform S3 Backend Initialization

This directory contains Terraform code for setting up the S3 backend for the Spack Terraform configuration. **This is entirely separate from the main Terraform configuration, and is used to set up the remote state bucket for that Terraform configuration.** For the main configuration, see the [terraform](../terraform) directory.

## Usage

This Terraform configuration is intended to be run **once** to set up the S3 backend for the main Terraform configuration's state file. It is not intended to be run again after that; **changes to this should be rare, and great care should be taken to ensure the remote state file is not lost or corrupted**. If you need to re-run it, follow the steps below.

1. From the root of the `spack-infrastructure` repository, navigate to the `terraform-bootstrap` directory.
   ```
   cd terraform-bootstrap/
   ```
2. Fetch the Terraform state from AWS secret manager:
    ```
    aws secretsmanager get-secret-value \
        --region us-east-1 \
        --secret-id terraform-bootstrap-tfstate \
        --query SecretString --output text \
        | jq -r '.["terraform.tfstate"]' \
        | tr -d '\n\r ' \
        | base64 --decode > terraform.tfstate
    ```
3. Initialize the Terraform backend:
   ```
   terraform init
   ```
4. Run a Terraform plan to verify that the backend is set up correctly:
   ```
   terraform plan
   ```
5. From this point on, you can run `terraform apply` to make changes to the infrastructure.
6. If any changes are made to the Terraform configuration, ensure that you write the base64-encoded updated version of the `terraform.tfstate` to the `terraform-bootstrap-tfstate` secret in AWS Secrets Manager.
