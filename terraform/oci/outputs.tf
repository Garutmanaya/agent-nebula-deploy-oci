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

output "ssh_command" {
  description = "Example SSH command."
  value       = "ssh ubuntu@${oci_core_instance.agent_nebula.public_ip}"
}

output "vcn_id" {
  value = oci_core_vcn.agent_nebula.id
}

output "subnet_id" {
  value = oci_core_subnet.public.id
}

output "ubuntu_image_ocid" {
  description = "Canonical Ubuntu image selected dynamically for the configured shape."
  value       = local.ubuntu_image_ocid
}
