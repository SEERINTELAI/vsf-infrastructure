variable "libvirt_uri" {
  description = "Libvirt connection URI"
  type        = string
  default     = "qemu:///system"
}

variable "storage_pool" {
  type    = string
  default = "default"
}

variable "network_bridge" {
  type    = string
  default = "ovs-br0"
}

variable "base_image_url" {
  type    = string
  default = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}

variable "control_plane_count" {
  type    = number
  default = 3
}

variable "control_plane_vcpu" {
  type    = number
  default = 8
}

variable "control_plane_memory_mb" {
  type    = number
  default = 32768
}

variable "control_plane_disk_gb" {
  type    = number
  default = 100
}

variable "worker_count" {
  type    = number
  default = 10
}

variable "worker_vcpu" {
  type    = number
  default = 4
}

variable "worker_memory_mb" {
  type    = number
  default = 16384
}

variable "worker_disk_gb" {
  type    = number
  default = 50
}

variable "gpu_worker_count" {
  type    = number
  default = 8
}

variable "gpu_worker_vcpu" {
  type    = number
  default = 8
}

variable "gpu_worker_memory_mb" {
  type    = number
  default = 32768
}

variable "gpu_worker_disk_gb" {
  type    = number
  default = 100
}

variable "infra_vms" {
  type = map(object({
    vcpu      = number
    memory_mb = number
    disk_gb   = number
  }))
  default = {
    prometheus = { vcpu = 4, memory_mb = 16384, disk_gb = 200 }
    dns        = { vcpu = 2, memory_mb = 4096, disk_gb = 20 }
    storage    = { vcpu = 4, memory_mb = 16384, disk_gb = 500 }
  }
}

variable "cluster_network_cidr" {
  type    = string
  default = "10.100.0.0/24"
}

variable "storage_network_cidr" {
  type    = string
  default = "10.200.0.0/24"
}

variable "use_hugepages" {
  type    = bool
  default = true
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "project" {
  type    = string
  default = "vsf"
}
