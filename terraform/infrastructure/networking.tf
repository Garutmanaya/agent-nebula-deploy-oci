# Minimal public OCI network used for SSH bootstrap and outbound Cloudflare connectivity.
resource "oci_core_vcn" "agent_nebula" {
  compartment_id = var.compartment_ocid
  cidr_blocks     = [var.vcn_cidr]
  display_name    = "agentnebula-vcn"
  dns_label       = var.vcn_dns_label
  freeform_tags   = var.freeform_tags
}

resource "oci_core_internet_gateway" "agent_nebula" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.agent_nebula.id
  display_name   = "agentnebula-internet-gateway"
  enabled        = true
  freeform_tags  = var.freeform_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.agent_nebula.id
  display_name   = "agentnebula-public-route-table"
  freeform_tags  = var.freeform_tags

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.agent_nebula.id
    description       = "Internet access for the public Agent Nebula subnet"
  }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.agent_nebula.id
  display_name   = "agentnebula-public-security-list"
  freeform_tags  = var.freeform_tags

  ingress_security_rules {
    protocol    = "6"
    source      = var.ssh_source_cidr
    source_type = "CIDR_BLOCK"
    description = "SSH administration"

    tcp_options {
      min = 22
      max = 22
    }
  }

  egress_security_rules {
    protocol         = "all"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    description      = "Outbound Internet access"
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.agent_nebula.id
  cidr_block                 = var.subnet_cidr
  display_name               = "agentnebula-public-subnet"
  dns_label                  = var.subnet_dns_label
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.public.id]
  prohibit_public_ip_on_vnic = false
  prohibit_internet_ingress  = false
  freeform_tags              = var.freeform_tags
}
