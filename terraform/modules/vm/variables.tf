# =============================================================================
# Virtual Server Farm - VM Module Variables
# =============================================================================

# =============================================================================
# Required Variables
# =============================================================================

variable "vm_name" {
  description = "Name of the virtual machine"
  type        = string
  
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.vm_name))
    error_message = "VM name must start with a letter and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "vm_type" {
  description = "Type of VM: control_plane, worker, or gpu_worker"
  type        = string
  
  validation {
    condition     = contains(["control_plane", "worker", "gpu_worker"], var.vm_type)
    error_message = "VM type must be one of: control_plane, worker, gpu_worker."
  }
}

variable "ip_address" {
  description = "Static IP address for the VM (CIDR notation, e.g., 10.0.0.10/24)"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "network_name" {
  description = "Libvirt network name"
  type        = string
  default     = "vsf-cluster"
}

variable "management_network" {
  description = "Optional management network name"
  type        = string
  default     = null
}

variable "gateway" {
  description = "Network gateway IP"
  type        = string
  default     = "10.0.0.1"
}

variable "dns_servers" {
  description = "DNS server IPs"
  type        = list(string)
  default     = ["10.0.0.1", "8.8.8.8"]
}

variable "network_cidr" {
  description = "Network CIDR"
  type        = string
  default     = "10.0.0.0/24"
}

# =============================================================================
# Resource Overrides (optional)
# =============================================================================

variable "vcpus" {
  description = "Number of vCPUs (overrides vm_type default)"
  type        = number
  default     = null
}

variable "memory_mb" {
  description = "Memory in MB (overrides vm_type default)"
  type        = number
  default     = null
}

variable "disk_size_gb" {
  description = "Root disk size in GB (overrides vm_type default)"
  type        = number
  default     = null
}

variable "data_disk_size_gb" {
  description = "Additional data disk size in GB (0 = no data disk)"
  type        = number
  default     = 0
}

# =============================================================================
# Storage Configuration
# =============================================================================

variable "storage_pool" {
  description = "Libvirt storage pool name"
  type        = string
  default     = "default"
}

variable "base_image_url" {
  description = "URL or path to base cloud image"
  type        = string
  default     = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
}

# =============================================================================
# CPU Configuration
# =============================================================================

variable "cpu_mode" {
  description = "CPU mode (host-model, host-passthrough, custom)"
  type        = string
  default     = "host-passthrough"
}

variable "use_hugepages" {
  description = "Use HugePages for VM memory"
  type        = bool
  default     = true
}

# =============================================================================
# GPU Passthrough (for gpu_worker)
# =============================================================================

variable "gpu_pci_addresses" {
  description = "List of GPU PCI addresses for passthrough (e.g., ['16:00.0', '40:00.0'])"
  type        = list(string)
  default     = []
}

# =============================================================================
# VirtualBMC Configuration
# =============================================================================

variable "enable_vbmc" {
  description = "Enable VirtualBMC IPMI simulation"
  type        = bool
  default     = true
}

variable "vbmc_port" {
  description = "VirtualBMC IPMI port"
  type        = number
  default     = 6230
}

variable "vbmc_username" {
  description = "VirtualBMC IPMI username"
  type        = string
  default     = "admin"
}

variable "vbmc_password" {
  description = "VirtualBMC IPMI password"
  type        = string
  default     = "password"
  sensitive   = true
}

# =============================================================================
# Lifecycle
# =============================================================================

variable "autostart" {
  description = "Auto-start VM on host boot"
  type        = bool
  default     = true
}

variable "timezone" {
  description = "VM timezone"
  type        = string
  default     = "UTC"
}

variable "ntp_servers" {
  description = "NTP server addresses"
  type        = list(string)
  default     = ["0.pool.ntp.org", "1.pool.ntp.org"]
}
