# Infrastructure identifiers consumed by the application Terraform root.
output "instance_id" {
  description = "OCI instance OCID."
  value       = oci_core_instance.agent_nebula.id
}

output "instance_public_ip" {
  description = "Ephemeral public IPv4 address used for bootstrap SSH."
  value       = oci_core_instance.agent_nebula.public_ip
}

output "instance_private_ip" {
  description = "Private IPv4 address inside the Agent Nebula VCN."
  value       = oci_core_instance.agent_nebula.private_ip
}

output "vcn_id" {
  description = "Agent Nebula VCN OCID."
  value       = oci_core_vcn.agent_nebula.id
}

output "subnet_id" {
  description = "Agent Nebula public subnet OCID."
  value       = oci_core_subnet.public.id
}

output "vault_ocid" {
  description = "OCI Vault OCID used as the authoritative Agent Nebula security store."
  value       = oci_kms_vault.agent_nebula.id
}

output "vault_key_ocid" {
  description = "OCI Vault encryption-key OCID used for Agent Nebula secrets."
  value       = oci_kms_key.agent_nebula.id
}

output "compartment_ocid" {
  description = "OCI compartment containing Agent Nebula resources."
  value       = var.compartment_ocid
}

output "dynamic_group_name" {
  description = "Dynamic Group that grants the VM Instance Principal access to Vault."
  value       = oci_identity_dynamic_group.agent_nebula.name
}

output "ubuntu_image_ocid" {
  description = "Canonical Ubuntu image selected dynamically for the configured shape."
  value       = local.ubuntu_image_ocid
}
