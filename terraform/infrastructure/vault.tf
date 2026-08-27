# OCI Vault and software-protected master key for durable Agent Nebula security material.
resource "oci_kms_vault" "agent_nebula" {
  compartment_id = var.compartment_ocid
  display_name   = var.vault_display_name
  vault_type     = "DEFAULT"
  freeform_tags  = var.freeform_tags
}

resource "oci_kms_key" "agent_nebula" {
  compartment_id      = var.compartment_ocid
  display_name        = var.vault_key_display_name
  management_endpoint = oci_kms_vault.agent_nebula.management_endpoint
  protection_mode     = "SOFTWARE"
  freeform_tags       = var.freeform_tags

  key_shape {
    algorithm = "AES"
    length    = 32
  }
}
