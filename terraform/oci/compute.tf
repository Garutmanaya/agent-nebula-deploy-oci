resource "oci_core_instance" "agent_nebula" {
  availability_domain = local.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = var.instance_name
  shape               = var.shape
  freeform_tags       = var.freeform_tags

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    display_name     = "${var.instance_name}-vnic"
    hostname_label   = var.instance_name
  }

  source_details {
    source_type             = "image"
    source_id               = local.ubuntu_image_ocid
    boot_volume_size_in_gbs = var.boot_volume_size_gbs
  }

  metadata = {
    ssh_authorized_keys = file(pathexpand(var.ssh_public_key_path))
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      create_swap = var.create_swap
    }))
  }

  lifecycle {
    precondition {
      condition     = length(data.oci_core_images.ubuntu.images) > 0
      error_message = "No Canonical Ubuntu image compatible with the selected OCI shape/version was found."
    }
  }
}
