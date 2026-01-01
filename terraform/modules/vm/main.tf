# =============================================================================
# Virtual Server Farm - Base VM Module
# =============================================================================
# This module creates libvirt VMs for the Virtual Server Farm cluster.
# Supports control plane, worker, and GPU worker node types.
#
# Author: Agent (Task 97, fixed by Task 99)
# Created: 2026-01-01
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
# Local Variables
# =============================================================================

locals {
  # VM type configurations
  vm_configs = {
    control_plane = {
      vcpus        = 4
      memory_mb    = 8192
      disk_size_gb = 100
    }
    worker = {
      vcpus        = 8
      memory_mb    = 32768
      disk_size_gb = 200
    }
    gpu_worker = {
      vcpus        = 16
      memory_mb    = 65536
      disk_size_gb = 500
    }
  }
  
  # Get config for this VM type
  config = local.vm_configs[var.vm_type]
  
  # Allow override of resources
  final_vcpus   = var.vcpus != null ? var.vcpus : local.config.vcpus
  final_memory  = var.memory_mb != null ? var.memory_mb : local.config.memory_mb
  final_disk    = var.disk_size_gb != null ? var.disk_size_gb : local.config.disk_size_gb
}

# =============================================================================
# Cloud-Init Configuration
# =============================================================================

data "template_file" "user_data" {
  template = file("${path.module}/templates/cloud-init.yaml")
  
  vars = {
    hostname     = var.vm_name
    ssh_key      = var.ssh_public_key
    timezone     = var.timezone
    ntp_servers  = join(",", var.ntp_servers)
  }
}

data "template_file" "network_config" {
  template = file("${path.module}/templates/network-config.yaml")
  
  vars = {
    ip_address   = var.ip_address
    gateway      = var.gateway
    dns_servers  = join(",", var.dns_servers)
    network_cidr = var.network_cidr
  }
}

resource "libvirt_cloudinit_disk" "cloudinit" {
  name           = "${var.vm_name}-cloudinit.iso"
  pool           = var.storage_pool
  user_data      = data.template_file.user_data.rendered
  network_config = data.template_file.network_config.rendered
}

# =============================================================================
# Base Volume (from cloud image)
# =============================================================================

resource "libvirt_volume" "base" {
  name   = "${var.vm_name}-base.qcow2"
  pool   = var.storage_pool
  source = var.base_image_url
  format = "qcow2"
}

# =============================================================================
# VM Root Volume (resized from base)
# =============================================================================

resource "libvirt_volume" "root" {
  name           = "${var.vm_name}-root.qcow2"
  pool           = var.storage_pool
  base_volume_id = libvirt_volume.base.id
  size           = local.final_disk * 1024 * 1024 * 1024
  format         = "qcow2"
}

# =============================================================================
# Additional Data Volume (optional)
# =============================================================================

resource "libvirt_volume" "data" {
  count  = var.data_disk_size_gb > 0 ? 1 : 0
  name   = "${var.vm_name}-data.qcow2"
  pool   = var.storage_pool
  size   = var.data_disk_size_gb * 1024 * 1024 * 1024
  format = "qcow2"
}

# =============================================================================
# Virtual Machine
# =============================================================================

resource "libvirt_domain" "vm" {
  name       = var.vm_name
  memory     = local.final_memory
  vcpu       = local.final_vcpus
  qemu_agent = true
  autostart  = var.autostart

  # CPU configuration
  cpu {
    mode = var.cpu_mode
  }

  # Cloud-init disk
  cloudinit = libvirt_cloudinit_disk.cloudinit.id

  # Root disk
  disk {
    volume_id = libvirt_volume.root.id
    scsi      = true
  }

  # Data disk (optional)
  dynamic "disk" {
    for_each = var.data_disk_size_gb > 0 ? [1] : []
    content {
      volume_id = libvirt_volume.data[0].id
      scsi      = true
    }
  }

  # Network interface
  network_interface {
    network_name   = var.network_name
    wait_for_lease = true
    hostname       = var.vm_name
  }

  # Management network (optional)
  dynamic "network_interface" {
    for_each = var.management_network != null ? [1] : []
    content {
      network_name = var.management_network
    }
  }

  # Console for debugging
  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  console {
    type        = "pty"
    target_type = "virtio"
    target_port = "1"
  }

  # Graphics (VNC for management)
  graphics {
    type           = "vnc"
    listen_type    = "address"
    listen_address = "0.0.0.0"
    autoport       = true
  }

  # Lifecycle
  lifecycle {
    ignore_changes = [
      network_interface,
    ]
  }
}

# =============================================================================
# VirtualBMC Registration (for IPMI simulation)
# =============================================================================

resource "null_resource" "vbmc_registration" {
  count = var.enable_vbmc ? 1 : 0

  depends_on = [libvirt_domain.vm]

  provisioner "local-exec" {
    command = <<-EOT
      vbmc add ${var.vm_name} \
        --port ${var.vbmc_port} \
        --username ${var.vbmc_username} \
        --password ${var.vbmc_password} \
        --libvirt-uri qemu:///system || true
      vbmc start ${var.vm_name} || true
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      vbmc stop ${self.triggers.vm_name} || true
      vbmc delete ${self.triggers.vm_name} || true
    EOT
  }

  triggers = {
    vm_name = var.vm_name
  }
}
