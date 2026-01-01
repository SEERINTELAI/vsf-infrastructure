# VSF Infrastructure

Terraform infrastructure-as-code for the Virtual Server Farm.

## Quick Start

1. Clone: `git clone git@github.com:SEERINTELAI/vsf-infrastructure.git`
2. Configure: `cp terraform/terraform.tfvars.example terraform/terraform.tfvars`
3. Deploy: `cd terraform && terraform init && terraform apply`

## Architecture

- 3 Control Plane VMs
- 10 Standard Workers
- 8 GPU Workers
- 24 Total VMs
