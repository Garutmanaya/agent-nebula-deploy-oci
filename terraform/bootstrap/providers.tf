# AWS provider used only to create the remote Terraform-state bucket.
provider "aws" {
  region = var.aws_region
}
