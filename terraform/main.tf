# VSF Infrastructure - Main Terraform Configuration

provider "libvirt" {
  uri = var.libvirt_uri
}

# Storage Pool
resource "libvirt_pool" "vsf_pool" {
  name = var.storage_pool_name
  type = "dir"
  path = var.storage_pool_path
}

# Base Image
resource "libvirt_volume" "base_image" {
  name   = "ubuntu-22.04-base.qcow2"
  pool   = libvirt_pool.vsf_pool.name
  source = var.base_image_url
  format = "qcow2"
}

# Cluster Network
resource "libvirt_network" "cluster" {
  name      = "vsf-cluster"
  mode      = "nat"
  domain    = "vsf.local"
  autostart = true
  addresses = [var.cluster_network_cidr]
  
  dhcp {
    enabled = true
  }
}

# Control Plane VMs
resource "libvirt_volume" "control_plane_disk" {
  count          = var.control_plane_count
  name           = "k8s-master-${count.index + 1}.qcow2"
  pool           = libvirt_pool.vsf_pool.name
  base_volume_id = libvirt_volume.base_image.id
  size           = 107374182400  # 100GB
  format         = "qcow2"
}

resource "libvirt_domain" "control_plane" {
  count  = var.control_plane_count
  name   = "k8s-master-${count.index + 1}"
  memory = var.control_plane_memory_mb
  vcpu   = var.control_plane_vcpus

  disk {
    volume_id = libvirt_volume.control_plane_disk[count.index].id
  }

  network_interface {
    network_id     = libvirt_network.cluster.id
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }
}

# Worker VMs
resource "libvirt_volume" "worker_disk" {
  count          = var.worker_count
  name           = "worker-${count.index + 1}.qcow2"
  pool           = libvirt_pool.vsf_pool.name
  base_volume_id = libvirt_volume.base_image.id
  size           = 53687091200  # 50GB
  format         = "qcow2"
}

resource "libvirt_domain" "worker" {
  count  = var.worker_count
  name   = "worker-${count.index + 1}"
  memory = var.worker_memory_mb
  vcpu   = var.worker_vcpus

  disk {
    volume_id = libvirt_volume.worker_disk[count.index].id
  }

  network_interface {
    network_id     = libvirt_network.cluster.id
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }
}

# GPU Worker VMs
resource "libvirt_volume" "gpu_worker_disk" {
  count          = var.gpu_worker_count
  name           = "gpu-worker-${count.index + 1}.qcow2"
  pool           = libvirt_pool.vsf_pool.name
  base_volume_id = libvirt_volume.base_image.id
  size           = 107374182400  # 100GB
  format         = "qcow2"
}

resource "libvirt_domain" "gpu_worker" {
  count  = var.gpu_worker_count
  name   = "gpu-worker-${count.index + 1}"
  memory = var.gpu_worker_memory_mb
  vcpu   = var.gpu_worker_vcpus

  disk {
    volume_id = libvirt_volume.gpu_worker_disk[count.index].id
  }

  network_interface {
    network_id     = libvirt_network.cluster.id
    wait_for_lease = true
  }

  cpu {
    mode = "host-passthrough"
  }
}
