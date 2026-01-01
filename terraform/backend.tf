# Terraform State Backend Configuration

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.7.6"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }

  # Azure Blob Storage backend
  backend "azurerm" {
    resource_group_name  = "vsf-terraform-state"
    storage_account_name = "vsfterraformstate"
    container_name       = "tfstate"
    key                  = "vsf-infrastructure.tfstate"
  }
}
