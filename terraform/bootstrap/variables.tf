# Operator-configurable Terraform-state bootstrap inputs.
variable "aws_region" {
  description = "AWS region that owns the Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name used only for Agent Nebula Terraform state."
  type        = string
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty state bucket. Keep false for normal use."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to the Terraform state bucket."
  type        = map(string)
  default = {
    project = "agent-nebula"
    purpose = "terraform-state"
    managed = "terraform"
  }
}
