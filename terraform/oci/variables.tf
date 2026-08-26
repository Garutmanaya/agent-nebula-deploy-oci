variable "region" {
  description = "OCI region identifier, for example us-ashburn-1."
  type        = string
}

variable "oci_profile" {
  description = "Profile name from ~/.oci/config used by the OCI Terraform provider."
  type        = string
  default     = "DEFAULT"
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
  description = "OCI compute shape. VM.Standard.A1.Flex is the ARM64 Always Free target."
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
  description = "Boot volume size. Keep this within the tenancy's free storage allowance."
  type        = number
  default     = 50
}

variable "ssh_public_key_path" {
  description = "Local path to the SSH public key installed for the ubuntu user."
  type        = string
}

variable "ssh_source_cidr" {
  description = "CIDR allowed to reach TCP/22. Use a /32 when possible. 0.0.0.0/0 is acceptable only for initial key-only bootstrap."
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
  description = "Optional exact availability-domain name. When null, Terraform uses the first AD returned for the tenancy."
  type        = string
  default     = null
}

variable "create_swap" {
  description = "Create a 2 GiB swap file through cloud-init."
  type        = bool
  default     = true
}

variable "freeform_tags" {
  description = "Free-form tags applied to OCI resources where supported."
  type        = map(string)
  default = {
    project = "agent-nebula"
    managed = "terraform"
  }
}
