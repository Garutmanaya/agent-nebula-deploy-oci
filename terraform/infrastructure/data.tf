# OCI discovery used to select the availability domain and compatible Ubuntu ARM64 image.
data "oci_identity_availability_domains" "this" {
  compartment_id = var.compartment_ocid
}

data "oci_core_images" "ubuntu" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = var.ubuntu_version
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  availability_domain = coalesce(
    var.availability_domain_name,
    data.oci_identity_availability_domains.this.availability_domains[0].name,
  )

  ubuntu_image_ocid = data.oci_core_images.ubuntu.images[0].id
}
