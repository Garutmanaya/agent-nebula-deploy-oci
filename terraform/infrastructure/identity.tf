# Instance Principal Dynamic Group and least-scope Vault access policy.
resource "oci_identity_dynamic_group" "agent_nebula" {
  compartment_id = var.tenancy_ocid
  name           = var.dynamic_group_name
  description    = "Instance Principal identity for the Agent Nebula OCI VM"
  matching_rule  = "ALL {instance.id = '${oci_core_instance.agent_nebula.id}'}"
  freeform_tags  = var.freeform_tags
}

resource "oci_identity_policy" "agent_nebula_vault" {
  compartment_id = var.tenancy_ocid
  name           = var.vault_policy_name
  description    = "Allow the Agent Nebula VM to create, restore, and read its Vault-backed security material"

  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.agent_nebula.name} to manage secret-family in compartment id ${var.compartment_ocid} where target.vault.id='${oci_kms_vault.agent_nebula.id}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.agent_nebula.name} to use keys in compartment id ${var.compartment_ocid} where target.key.id='${oci_kms_key.agent_nebula.id}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.agent_nebula.name} to use vaults in compartment id ${var.compartment_ocid} where target.vault.id='${oci_kms_vault.agent_nebula.id}'",
  ]
}
