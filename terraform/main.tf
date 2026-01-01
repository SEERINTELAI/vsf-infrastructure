# VSF Infrastructure - Main Terraform Configuration
# Simplified version using default pool for Track A deployment

provider "libvirt" {
  uri = var.libvirt_uri
}

# Read SSH public key
locals {
  ssh_key = file("${path.module}/ssh_key.pub")
}

# Base Image in default pool (has proper permissions)
resource "libvirt_volume" "base_image" {
  name   = "vsf-ubuntu-22.04-base.qcow2"
  pool   = "default"
  source = var.base_image_url
  format = "qcow2"
}

# ============================================
# Control Plane VMs
# ============================================
data "template_file" "control_plane_user_data" {
  count    = var.control_plane_count
  template = file("${path.module}/cloud-init/user-data.tftpl")
  vars = {
    hostname = "vsf-cp-${count.index + 1}"
    ssh_key  = local.ssh_key
  }
}

resource "libvirt_cloudinit_disk" "control_plane_init" {
  count     = var.control_plane_count
  name      = "vsf-cp-${count.index + 1}-init.iso"
  pool      = "default"
  user_data = data.template_file.control_plane_user_data[count.index].rendered
}

resource "libvirt_volume" "control_plane_disk" {
  count          = var.control_plane_count
  name           = "vsf-cp-${count.index + 1}.qcow2"
  pool           = "default"
  base_volume_id = libvirt_volume.base_image.id
  size           = var.control_plane_disk_gb * 1073741824
  format         = "qcow2"
}

resource "libvirt_domain" "control_plane" {
  count  = var.control_plane_count
  name   = "vsf-cp-${count.index + 1}"
  memory = var.control_plane_memory_mb
  vcpu   = var.control_plane_vcpu

  cloudinit = libvirt_cloudinit_disk.control_plane_init[count.index].id

  disk {
    volume_id = libvirt_volume.control_plane_disk[count.index].id
  }

  network_interface {
    network_name   = "vsf-cluster"
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

# ============================================
# Worker VMs
# ============================================
data "template_file" "worker_user_data" {
  count    = var.worker_count
  template = file("${path.module}/cloud-init/user-data.tftpl")
  vars = {
    hostname = "vsf-worker-${count.index + 1}"
    ssh_key  = local.ssh_key
  }
}

resource "libvirt_cloudinit_disk" "worker_init" {
  count     = var.worker_count
  name      = "vsf-worker-${count.index + 1}-init.iso"
  pool      = "default"
  user_data = data.template_file.worker_user_data[count.index].rendered
}

resource "libvirt_volume" "worker_disk" {
  count          = var.worker_count
  name           = "vsf-worker-${count.index + 1}.qcow2"
  pool           = "default"
  base_volume_id = libvirt_volume.base_image.id
  size           = var.worker_disk_gb * 1073741824
  format         = "qcow2"
}

resource "libvirt_domain" "worker" {
  count  = var.worker_count
  name   = "vsf-worker-${count.index + 1}"
  memory = var.worker_memory_mb
  vcpu   = var.worker_vcpu

  cloudinit = libvirt_cloudinit_disk.worker_init[count.index].id

  disk {
    volume_id = libvirt_volume.worker_disk[count.index].id
  }

  network_interface {
    network_name   = "vsf-cluster"
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

# ============================================
# GPU Worker VMs
# ============================================
data "template_file" "gpu_worker_user_data" {
  count    = var.gpu_worker_count
  template = file("${path.module}/cloud-init/user-data.tftpl")
  vars = {
    hostname = "vsf-gpu-${count.index + 1}"
    ssh_key  = local.ssh_key
  }
}

resource "libvirt_cloudinit_disk" "gpu_worker_init" {
  count     = var.gpu_worker_count
  name      = "vsf-gpu-${count.index + 1}-init.iso"
  pool      = "default"
  user_data = data.template_file.gpu_worker_user_data[count.index].rendered
}

resource "libvirt_volume" "gpu_worker_disk" {
  count          = var.gpu_worker_count
  name           = "vsf-gpu-${count.index + 1}.qcow2"
  pool           = "default"
  base_volume_id = libvirt_volume.base_image.id
  size           = var.gpu_worker_disk_gb * 1073741824
  format         = "qcow2"
}

resource "libvirt_domain" "gpu_worker" {
  count  = var.gpu_worker_count
  name   = "vsf-gpu-${count.index + 1}"
  memory = var.gpu_worker_memory_mb
  vcpu   = var.gpu_worker_vcpu

  cloudinit = libvirt_cloudinit_disk.gpu_worker_init[count.index].id

  disk {
    volume_id = libvirt_volume.gpu_worker_disk[count.index].id
  }

  network_interface {
    network_name   = "vsf-cluster"
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

# ============================================
# GPU Passthrough - Attach GPUs to GPU Worker VMs
# ============================================
resource "null_resource" "attach_gpus" {
  count = var.gpu_worker_count

  depends_on = [libvirt_domain.gpu_worker]

  triggers = {
    vm_id = libvirt_domain.gpu_worker[count.index].id
  }

  provisioner "local-exec" {
    command = "${path.module}/attach_gpu.sh ${count.index}"
  }
}
