# OCI infrastructure root and remote S3 backend constraints.
terraform {
  required_version = ">= 1.6.0"

  backend "s3" {}

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 8.0, < 9.0"
    }
  }
}
