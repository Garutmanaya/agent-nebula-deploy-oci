# Terraform State Bootstrap

This root is intentionally applied with local Terraform state exactly once. It creates the private,
versioned, encrypted S3 bucket used by the OCI infrastructure and application Terraform roots.

```bash
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
make tf-bootstrap-init
make tf-bootstrap-plan
make tf-bootstrap-apply
```

After apply, export the two outputs before initializing the remaining roots:

```bash
export TF_STATE_BUCKET="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_name)"
export TF_STATE_REGION="$(terraform -chdir=terraform/bootstrap output -raw state_bucket_region)"
```

The bucket has `prevent_destroy = true` by design. Terraform state must not disappear when OCI
infrastructure is destroyed and rebuilt.
