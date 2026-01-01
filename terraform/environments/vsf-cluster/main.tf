# =============================================================================
# Virtual Server Farm - Cluster Deployment
# =============================================================================
# Deploys the full 24-node VSF cluster:
# - 3 Control Plane nodes (K3s server)
# - 10 Standard Worker nodes
# - 8 GPU Worker nodes (1 GPU each)
# - 3 Infrastructure nodes (monitoring, storage)
#
# Author: Agent (Task 97-100)
# =============================================================================

terraform {
  required_version = ">= 1.0.0"
  
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.7.0"
    }
  }
}

# =============================================================================
# Provider Configuration
# =============================================================================

provider "libvirt" {
  uri = "qemu:///system"
}

# =============================================================================
# Variables
# =============================================================================

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
  default     = ""
}

variable "base_image_url" {
  description = "Ubuntu cloud image URL"
  type        = string
  default     = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}

# GPU PCI addresses on Bizon1 (8x NVIDIA H100/H200)
variable "gpu_pci_addresses" {
  description = "Available GPU PCI addresses"
  type        = list(string)
  default = [
    "16:00.0",   # GPU 0
    "40:00.0",   # GPU 1
    "94:00.0",   # GPU 2
    "be:00.0",   # GPU 3
    "1:16:00.0", # GPU 4 (domain 1)
    "1:6a:00.0", # GPU 5 (domain 1)
    "1:94:00.0", # GPU 6 (domain 1)
    "1:be:00.0", # GPU 7 (domain 1)
  ]
}

# =============================================================================
# Local Variables
# =============================================================================

locals {
  # Read SSH key from file if not provided
  ssh_key = var.ssh_public_key != "" ? var.ssh_public_key : file("~/.ssh/id_rsa.pub")
  
  # Network configuration
  network_name = "vsf-cluster"
  gateway      = "10.0.0.1"
  dns_servers  = ["10.0.0.1", "8.8.8.8"]
  
  # VirtualBMC port base
  vbmc_port_base = 6230
}

# =============================================================================
# Network
# =============================================================================

resource "libvirt_network" "vsf_cluster" {
  name      = local.network_name
  mode      = "nat"
  domain    = "vsf.local"
  addresses = ["10.0.0.0/24"]
  
  dhcp {
    enabled = false
  }
  
  dns {
    enabled    = true
    local_only = true
  }
}

# =============================================================================
# Storage Pool
# =============================================================================

resource "libvirt_pool" "vsf" {
  name = "vsf-storage"
  type = "dir"
  path = "/var/lib/libvirt/vsf-images"
}

# =============================================================================
# Control Plane Nodes (3)
# =============================================================================

module "control_plane" {
  source   = "../../modules/vm"
  count    = 3
  
  vm_name        = "vsf-cp-${count.index + 1}"
  vm_type        = "control_plane"
  ip_address     = "10.0.0.${10 + count.index}/24"
  ssh_public_key = local.ssh_key
  
  network_name   = libvirt_network.vsf_cluster.name
  storage_pool   = libvirt_pool.vsf.name
  gateway        = local.gateway
  dns_servers    = local.dns_servers
  base_image_url = var.base_image_url
  
  enable_vbmc = true
  vbmc_port   = local.vbmc_port_base + count.index
  
  depends_on = [libvirt_network.vsf_cluster, libvirt_pool.vsf]
}

# =============================================================================
# Standard Worker Nodes (10)
# =============================================================================

module "worker" {
  source   = "../../modules/vm"
  count    = 10
  
  vm_name        = "vsf-worker-${count.index + 1}"
  vm_type        = "worker"
  ip_address     = "10.0.0.${20 + count.index}/24"
  ssh_public_key = local.ssh_key
  
  network_name   = libvirt_network.vsf_cluster.name
  storage_pool   = libvirt_pool.vsf.name
  gateway        = local.gateway
  dns_servers    = local.dns_servers
  base_image_url = var.base_image_url
  
  enable_vbmc = true
  vbmc_port   = local.vbmc_port_base + 3 + count.index  # Offset by control plane count
  
  depends_on = [libvirt_network.vsf_cluster, libvirt_pool.vsf]
}

# =============================================================================
# GPU Worker Nodes (8)
# =============================================================================

module "gpu_worker" {
  source   = "../../modules/vm"
  count    = 8
  
  vm_name        = "vsf-gpu-${count.index + 1}"
  vm_type        = "gpu_worker"
  ip_address     = "10.0.0.${40 + count.index}/24"
  ssh_public_key = local.ssh_key
  
  network_name      = libvirt_network.vsf_cluster.name
  storage_pool      = libvirt_pool.vsf.name
  gateway           = local.gateway
  dns_servers       = local.dns_servers
  base_image_url    = var.base_image_url
  
  # Each GPU worker gets one GPU
  gpu_pci_addresses = [var.gpu_pci_addresses[count.index]]
  
  enable_vbmc = true
  vbmc_port   = local.vbmc_port_base + 13 + count.index  # Offset by control + worker count
  
  depends_on = [libvirt_network.vsf_cluster, libvirt_pool.vsf]
}

# =============================================================================
# Infrastructure Nodes (3) - Monitoring, Storage, Ingress
# =============================================================================

module "infra" {
  source   = "../../modules/vm"
  count    = 3
  
  vm_name        = "vsf-infra-${count.index + 1}"
  vm_type        = "worker"  # Same specs as worker
  ip_address     = "10.0.0.${50 + count.index}/24"
  ssh_public_key = local.ssh_key
  
  network_name   = libvirt_network.vsf_cluster.name
  storage_pool   = libvirt_pool.vsf.name
  gateway        = local.gateway
  dns_servers    = local.dns_servers
  base_image_url = var.base_image_url
  
  # Larger disk for monitoring data
  data_disk_size_gb = 500
  
  enable_vbmc = true
  vbmc_port   = local.vbmc_port_base + 21 + count.index
  
  depends_on = [libvirt_network.vsf_cluster, libvirt_pool.vsf]
}

# =============================================================================
# Outputs
# =============================================================================

output "control_plane_ips" {
  description = "Control plane node IPs"
  value       = [for cp in module.control_plane : cp.ip_address]
}

output "worker_ips" {
  description = "Worker node IPs"
  value       = [for w in module.worker : w.ip_address]
}

output "gpu_worker_ips" {
  description = "GPU worker node IPs"
  value       = [for gw in module.gpu_worker : gw.ip_address]
}

output "infra_ips" {
  description = "Infrastructure node IPs"
  value       = [for i in module.infra : i.ip_address]
}

output "total_nodes" {
  description = "Total number of nodes"
  value       = 3 + 10 + 8 + 3  # 24 nodes
}

output "vbmc_ports" {
  description = "VirtualBMC ports for all nodes"
  value = {
    control_plane = [for i in range(3) : local.vbmc_port_base + i]
    workers       = [for i in range(10) : local.vbmc_port_base + 3 + i]
    gpu_workers   = [for i in range(8) : local.vbmc_port_base + 13 + i]
    infra         = [for i in range(3) : local.vbmc_port_base + 21 + i]
  }
}

output "ssh_commands" {
  description = "SSH commands for all nodes"
  value = concat(
    [for cp in module.control_plane : cp.ssh_command],
    [for w in module.worker : w.ssh_command],
    [for gw in module.gpu_worker : gw.ssh_command],
    [for i in module.infra : i.ssh_command]
  )
}
