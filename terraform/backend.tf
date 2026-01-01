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

  # Local backend for development
  backend "local" {
    path = "terraform.tfstate"
  }
}
