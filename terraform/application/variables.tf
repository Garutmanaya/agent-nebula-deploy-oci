# Non-secret application deployment inputs; secret tokens stay outside Terraform state.
variable "state_bucket" {
  description = "S3 bucket containing Agent Nebula Terraform state."
  type        = string
}

variable "state_region" {
  description = "AWS region containing the Terraform state bucket."
  type        = string
}

variable "infrastructure_state_key" {
  description = "S3 key containing terraform/infrastructure state."
  type        = string
  default     = "oci/infrastructure/terraform.tfstate"
}

variable "image_tag" {
  description = "Logical GHCR image tag to install. The target architecture suffix is appended automatically."
  type        = string
  default     = "latest"
}

variable "profile" {
  description = "Agent Nebula deployment profile; Cloudflare host integration is configured independently."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "cloudflare"], var.profile)
    error_message = "profile must be local or cloudflare."
  }
}

variable "deployment_phase" {
  description = "prepare initializes host material only; platform deploys/bootstrap Core services; applications deploys Explorer and Playground after API keys exist."
  type        = string
  default     = "platform"

  validation {
    condition     = contains(["prepare", "platform", "applications"], var.deployment_phase)
    error_message = "deployment_phase must be prepare, platform, or applications."
  }
}

variable "ssh_user" {
  description = "SSH user created by the Canonical Ubuntu OCI image."
  type        = string
  default     = "ubuntu"
}

variable "ssh_private_key_path" {
  description = "Operator-host path to the SSH private key. Only the path is stored in Terraform state."
  type        = string
}

variable "utils_repository_path" {
  description = "Path to the sibling agent-nebula-utils repository, relative to agent-nebula-deploy-oci or absolute."
  type        = string
  default     = "../agent-nebula-utils"
}
