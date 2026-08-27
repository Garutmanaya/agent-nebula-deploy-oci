# Stable backend coordinates consumed by later Terraform roots.
output "state_bucket_name" {
  description = "S3 bucket used by the infrastructure and application Terraform roots."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "state_bucket_region" {
  description = "AWS region containing the Terraform state bucket."
  value       = var.aws_region
}

output "infrastructure_state_key" {
  description = "Recommended S3 key for OCI infrastructure state."
  value       = "oci/infrastructure/terraform.tfstate"
}

output "application_state_key" {
  description = "Recommended S3 key for OCI application state."
  value       = "oci/application/terraform.tfstate"
}
