# Reuse the existing deployment lifecycle over SSH instead of reproducing application logic in HCL.
data "terraform_remote_state" "infrastructure" {
  backend = "s3"

  config = {
    bucket = var.state_bucket
    key    = var.infrastructure_state_key
    region = var.state_region
  }
}

locals {
  repository_root = abspath("${path.module}/../..")
  deployment_files = sort(concat(
    tolist(fileset(local.repository_root, "Makefile")),
    tolist(fileset(local.repository_root, "config/**")),
    tolist(fileset(local.repository_root, "deploy/**")),
    tolist(fileset(local.repository_root, "deployment/**")),
    tolist(fileset(local.repository_root, "scripts/*.py")),
  ))
  deployment_revision = sha256(join("", [
    for file in local.deployment_files : filesha256("${local.repository_root}/${file}")
  ]))
}

resource "terraform_data" "application" {
  triggers_replace = [
    data.terraform_remote_state.infrastructure.outputs.instance_id,
    var.release,
    var.profile,
    var.deployment_phase,
    local.deployment_revision,
  ]

  provisioner "local-exec" {
    working_dir = local.repository_root
    command = join(" ", [
      "python3 scripts/remote_application.py",
      "--host ${data.terraform_remote_state.infrastructure.outputs.instance_public_ip}",
      "--user ${var.ssh_user}",
      "--identity-file ${var.ssh_private_key_path}",
      "--utils-repository ${var.utils_repository_path}",
      "--release ${var.release}",
      "--profile ${var.profile}",
      "--phase ${var.deployment_phase}",
      "--compartment-ocid ${data.terraform_remote_state.infrastructure.outputs.compartment_ocid}",
      "--vault-ocid ${data.terraform_remote_state.infrastructure.outputs.vault_ocid}",
      "--vault-key-ocid ${data.terraform_remote_state.infrastructure.outputs.vault_key_ocid}",
    ])
  }
}
