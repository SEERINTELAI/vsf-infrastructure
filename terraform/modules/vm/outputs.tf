# =============================================================================
# Virtual Server Farm - VM Module Outputs
# =============================================================================

output "vm_id" {
  description = "Libvirt domain ID"
  value       = libvirt_domain.vm.id
}

output "vm_name" {
  description = "VM name"
  value       = libvirt_domain.vm.name
}

output "ip_address" {
  description = "VM IP address"
  value       = var.ip_address
}

output "mac_address" {
  description = "VM MAC address"
  value       = libvirt_domain.vm.network_interface[0].mac
}

output "vnc_port" {
  description = "VNC port for console access"
  value       = libvirt_domain.vm.graphics[0].listen_address
}

output "vcpus" {
  description = "Number of vCPUs allocated"
  value       = local.final_vcpus
}

output "memory_mb" {
  description = "Memory allocated in MB"
  value       = local.final_memory
}

output "disk_size_gb" {
  description = "Root disk size in GB"
  value       = local.final_disk
}

output "vm_type" {
  description = "VM type (control_plane, worker, gpu_worker)"
  value       = var.vm_type
}

output "gpu_count" {
  description = "Number of GPUs attached"
  value       = length(var.gpu_pci_addresses)
}

output "vbmc_port" {
  description = "VirtualBMC IPMI port (if enabled)"
  value       = var.enable_vbmc ? var.vbmc_port : null
}

output "ssh_command" {
  description = "SSH command to connect to VM"
  value       = "ssh ubuntu@${split("/", var.ip_address)[0]}"
}
