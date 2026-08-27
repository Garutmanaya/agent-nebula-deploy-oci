# OCI provider authenticated from the operator development host.
provider "oci" {
  region              = var.region
  config_file_profile = var.oci_profile
}
