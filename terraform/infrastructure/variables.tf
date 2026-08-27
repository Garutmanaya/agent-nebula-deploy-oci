# OCI network, compute, Vault, and IAM inputs.
variable "region" {
  description = "OCI region identifier, for example us-ashburn-1."
  type        = string
}

variable "oci_profile" {
  description = "Profile name from ~/.oci/config used by Terraform from the operator host."
  type        = string
  default     = "DEFAULT"
}

variable "tenancy_ocid" {
  description = "OCI tenancy OCID. Required for the instance-principal Dynamic Group."
  type        = string
}

variable "compartment_ocid" {
  description = "OCI compartment OCID where Agent Nebula resources are created."
  type        = string
}

variable "instance_name" {
  description = "Display name and hostname label for the Agent Nebula VM."
  type        = string
  default     = "agentnebula"
}

variable "shape" {
  description = "OCI Compute shape. VM.Standard.A1.Flex is the ARM64 Always Free target."
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "ocpus" {
  description = "Number of OCPUs allocated to the flexible shape."
  type        = number
  default     = 2
}

variable "memory_gbs" {
  description = "Memory allocated to the flexible shape in GiB."
  type        = number
  default     = 12
}

variable "boot_volume_size_gbs" {
  description = "Boot-volume size in GiB. Keep this within the tenancy free-storage allowance."
  type        = number
  default     = 50
}

variable "ssh_public_key_path" {
  description = "Operator-host path to the SSH public key installed for the ubuntu user."
  type        = string
}

variable "ssh_source_cidr" {
  description = "CIDR allowed to reach TCP/22 during bootstrap. Restrict when practical."
  type        = string
  default     = "0.0.0.0/0"
}

variable "vcn_cidr" {
  description = "IPv4 CIDR for the Agent Nebula VCN."
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "IPv4 CIDR for the public Agent Nebula subnet."
  type        = string
  default     = "10.0.0.0/24"
}

variable "vcn_dns_label" {
  description = "OCI internal DNS label for the VCN."
  type        = string
  default     = "agentnebula"
}

variable "subnet_dns_label" {
  description = "OCI internal DNS label for the public subnet."
  type        = string
  default     = "public"
}

variable "ubuntu_version" {
  description = "Canonical Ubuntu version used for the A1 instance."
  type        = string
  default     = "22.04"
}

variable "availability_domain_name" {
  description = "Optional exact availability-domain name. Null selects the first returned AD."
  type        = string
  default     = null
}

variable "create_swap" {
  description = "Create persistent swap. Disabled by default because runtime secrets live in /run."
  type        = bool
  default     = false
}

variable "vault_display_name" {
  description = "Display name for the standard OCI Vault used as the security source of truth."
  type        = string
  default     = "agent-nebula-vault"
}

variable "vault_key_display_name" {
  description = "Display name for the software-protected Vault master encryption key."
  type        = string
  default     = "agent-nebula-vault-key"
}

variable "dynamic_group_name" {
  description = "Name of the Dynamic Group that gives the VM an OCI Instance Principal."
  type        = string
  default     = "agent-nebula-instance-principals"
}

variable "vault_policy_name" {
  description = "Name of the IAM policy granting only the VM Dynamic Group access to Vault data."
  type        = string
  default     = "agent-nebula-vault-access"
}

variable "freeform_tags" {
  description = "Free-form tags applied to OCI resources where supported."
  type        = map(string)
  default = {
    project = "agent-nebula"
    managed = "terraform"
  }
}
