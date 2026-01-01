# Virtual Server Farm - VM Module

Terraform module for creating libvirt VMs in the Virtual Server Farm cluster.

## Features

- **Multiple VM Types**: control_plane, worker, gpu_worker with preset configurations
- **Cloud-Init**: Automatic VM configuration on first boot
- **HugePages Support**: Uses 2MB HugePages for optimal memory performance
- **GPU Passthrough**: VFIO-based GPU assignment for gpu_worker VMs
- **VirtualBMC**: Optional IPMI simulation for bare-metal-like management
- **Static IP**: Network configuration via cloud-init

## VM Type Defaults

| Type | vCPUs | Memory | Disk |
|------|-------|--------|------|
| control_plane | 4 | 8 GB | 100 GB |
| worker | 8 | 32 GB | 200 GB |
| gpu_worker | 16 | 64 GB | 500 GB |

## Usage

### Basic Control Plane Node

```hcl
module "control_plane_1" {
  source = "./modules/vm"

  vm_name        = "vsf-cp-1"
  vm_type        = "control_plane"
  ip_address     = "10.0.0.10/24"
  ssh_public_key = file("~/.ssh/id_rsa.pub")
  
  network_name = "vsf-cluster"
  gateway      = "10.0.0.1"
}
```

### Worker Node

```hcl
module "worker_1" {
  source = "./modules/vm"

  vm_name        = "vsf-worker-1"
  vm_type        = "worker"
  ip_address     = "10.0.0.20/24"
  ssh_public_key = file("~/.ssh/id_rsa.pub")
  
  # Optional: additional data disk
  data_disk_size_gb = 500
}
```

### GPU Worker Node

```hcl
module "gpu_worker_1" {
  source = "./modules/vm"

  vm_name        = "vsf-gpu-1"
  vm_type        = "gpu_worker"
  ip_address     = "10.0.0.30/24"
  ssh_public_key = file("~/.ssh/id_rsa.pub")
  
  # GPU passthrough - specify PCI addresses
  gpu_pci_addresses = ["16:00.0"]
  
  # VirtualBMC for IPMI management
  enable_vbmc = true
  vbmc_port   = 6230
}
```

### Multi-GPU Worker

```hcl
module "gpu_worker_multi" {
  source = "./modules/vm"

  vm_name        = "vsf-gpu-multi"
  vm_type        = "gpu_worker"
  ip_address     = "10.0.0.31/24"
  ssh_public_key = file("~/.ssh/id_rsa.pub")
  
  # Multiple GPUs
  gpu_pci_addresses = ["16:00.0", "40:00.0"]
  
  # Override resources for multi-GPU
  vcpus     = 32
  memory_mb = 131072  # 128 GB
}
```

## Requirements

### Host Prerequisites

1. **IOMMU Enabled**: Add `intel_iommu=on iommu=pt` to GRUB
2. **HugePages Configured**: `vm.nr_hugepages = 460800` (for 900GB)
3. **VFIO Modules**: vfio, vfio_pci, vfio_iommu_type1
4. **Libvirt**: With QEMU/KVM backend
5. **VirtualBMC**: For IPMI simulation (optional)

### Terraform Provider

```hcl
terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.7.0"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| vm_name | VM name | string | - | yes |
| vm_type | control_plane, worker, gpu_worker | string | - | yes |
| ip_address | Static IP (CIDR) | string | - | yes |
| ssh_public_key | SSH public key | string | - | yes |
| network_name | Libvirt network | string | "vsf-cluster" | no |
| gpu_pci_addresses | GPU PCI addresses | list(string) | [] | no |
| enable_vbmc | Enable VirtualBMC | bool | true | no |
| use_hugepages | Use HugePages | bool | true | no |

See `variables.tf` for full list.

## Outputs

| Name | Description |
|------|-------------|
| vm_id | Libvirt domain ID |
| vm_name | VM name |
| ip_address | VM IP address |
| mac_address | VM MAC address |
| ssh_command | SSH connection command |
| vbmc_port | VirtualBMC IPMI port |

## IPMI Management (VirtualBMC)

When `enable_vbmc = true`, VMs are registered with VirtualBMC:

```bash
# List VMs
vbmc list

# Power operations
ipmitool -I lanplus -H localhost -p 6230 -U admin -P password power status
ipmitool -I lanplus -H localhost -p 6230 -U admin -P password power on
ipmitool -I lanplus -H localhost -p 6230 -U admin -P password power off
ipmitool -I lanplus -H localhost -p 6230 -U admin -P password power reset
```

## Network Architecture

```
┌─────────────────────────────────────────────────┐
│                 vsf-cluster network             │
│                   10.0.0.0/24                   │
├─────────────────────────────────────────────────┤
│  Control Plane    │  Workers      │  GPU Workers│
│  10.0.0.10-12     │  10.0.0.20-29 │  10.0.0.30+ │
└─────────────────────────────────────────────────┘
```

## License

Internal use - Virtual Server Farm project
