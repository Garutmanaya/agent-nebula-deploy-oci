# Application-phase result coordinates.
output "instance_public_ip" {
  description = "OCI public IP used by the application deployment transport."
  value       = data.terraform_remote_state.infrastructure.outputs.instance_public_ip
}

output "deployment_phase" {
  description = "Last application phase applied through this Terraform root."
  value       = var.deployment_phase
}
