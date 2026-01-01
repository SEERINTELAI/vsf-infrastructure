output "control_plane_ids" {
  description = "IDs of control plane VMs"
  value       = libvirt_domain.control_plane[*].id
}

output "control_plane_names" {
  value = libvirt_domain.control_plane[*].name
}

output "worker_ids" {
  value = libvirt_domain.worker[*].id
}

output "worker_names" {
  value = libvirt_domain.worker[*].name
}

output "gpu_worker_ids" {
  value = libvirt_domain.gpu_worker[*].id
}

output "gpu_worker_names" {
  value = libvirt_domain.gpu_worker[*].name
}

output "cluster_summary" {
  value = {
    control_plane_count = var.control_plane_count
    worker_count        = var.worker_count
    gpu_worker_count    = var.gpu_worker_count
    total_vms           = var.control_plane_count + var.worker_count + var.gpu_worker_count
  }
}
