# Application orchestration root with independent remote Terraform state.
terraform {
  required_version = ">= 1.6.0"

  backend "s3" {}
}
