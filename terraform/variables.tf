variable "libvirt_uri" {
  description = "Libvirt connection URI"
  type        = string
  default     = "qemu:///system"
}

variable "base_image_url" {
  description = "URL for the base Ubuntu cloud image"
  type        = string
  default     = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}

# Control Plane Configuration
variable "control_plane_count" {
  description = "Number of control plane VMs"
  type        = number
  default     = 3
}

variable "control_plane_vcpu" {
  description = "vCPUs per control plane VM"
  type        = number
  default     = 8
}

variable "control_plane_memory_mb" {
  description = "Memory in MB per control plane VM"
  type        = number
  default     = 32768
}

variable "control_plane_disk_gb" {
  description = "Disk size in GB per control plane VM"
  type        = number
  default     = 100
}

# Worker Configuration
variable "worker_count" {
  description = "Number of standard worker VMs"
  type        = number
  default     = 10
}

variable "worker_vcpu" {
  description = "vCPUs per worker VM"
  type        = number
  default     = 4
}

variable "worker_memory_mb" {
  description = "Memory in MB per worker VM"
  type        = number
  default     = 16384
}

variable "worker_disk_gb" {
  description = "Disk size in GB per worker VM"
  type        = number
  default     = 50
}

# GPU Worker Configuration
variable "gpu_worker_count" {
  description = "Number of GPU worker VMs"
  type        = number
  default     = 8
}

variable "gpu_worker_vcpu" {
  description = "vCPUs per GPU worker VM"
  type        = number
  default     = 8
}

variable "gpu_worker_memory_mb" {
  description = "Memory in MB per GPU worker VM"
  type        = number
  default     = 32768
}

variable "gpu_worker_disk_gb" {
  description = "Disk size in GB per GPU worker VM"
  type        = number
  default     = 100
}

# Network Configuration
variable "cluster_network_cidr" {
  description = "CIDR for the cluster network"
  type        = string
  default     = "10.100.0.0/24"
}

variable "storage_network_cidr" {
  description = "CIDR for the storage network"
  type        = string
  default     = "10.200.0.0/24"
}

# Infrastructure VMs
variable "infra_vms" {
  description = "Infrastructure VM configurations"
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

# Feature Flags
variable "use_hugepages" {
  description = "Enable HugePages for VMs"
  type        = bool
  default     = true
}

variable "environment" {
  description = "Environment name (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "project" {
  description = "Project name"
  type        = string
  default     = "vsf"
}
