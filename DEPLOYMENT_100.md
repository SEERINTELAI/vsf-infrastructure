# Task 100: GPU Worker VMs Deployment

## Status: Partial Success - libvirtd Needs Restart

## Summary
8 GPU Worker VMs were created via Terraform but libvirtd became unresponsive during GPU passthrough attachment.

## VMs Created
- vsf-gpu-1 through vsf-gpu-8
- Each VM: 8 vCPU, 32GB RAM, 100GB disk
- Base image: Ubuntu 22.04 cloud image
- Network: vsf-cluster (NAT)

## GPU PCI Address Assignments
| VM | GPU PCI Address |
|----|-----------------|
| vsf-gpu-1 | 0000:16:00.0 |
| vsf-gpu-2 | 0000:40:00.0 |
| vsf-gpu-3 | 0000:94:00.0 |
| vsf-gpu-4 | 0000:be:00.0 |
| vsf-gpu-5 | 0001:16:00.0 |
| vsf-gpu-6 | 0001:6a:00.0 |
| vsf-gpu-7 | 0001:94:00.0 |
| vsf-gpu-8 | 0001:be:00.0 |

## Files Created/Modified
- `terraform/main.tf` - Added GPU worker resources with null_resource for GPU attachment
- `terraform/attach_gpu.sh` - Script to attach GPUs via virsh
- `terraform/gpu_passthrough.tf` - GPU PCI address configuration
- `terraform/ssh_key.pub` - SSH public key for cloud-init

## Terraform Resources in State
- `libvirt_domain.gpu_worker[0-7]` - 8 GPU worker domains (imported)
- `libvirt_volume.gpu_worker_disk[0-7]` - 8 disk volumes
- `libvirt_cloudinit_disk.gpu_worker_init[0-7]` - 8 cloud-init ISOs

## To Complete Deployment
After libvirtd is restarted (requires sudo):
```bash
sudo systemctl restart libvirtd

# Verify VMs
virsh list --all | grep vsf-gpu

# Attach GPUs manually if needed
cd terraform
for i in {0..7}; do ./attach_gpu.sh $i; done

# Start VMs
for i in {1..8}; do virsh start vsf-gpu-$i; done

# Verify GPU passthrough
for i in {1..8}; do
  echo "=== vsf-gpu-$i ==="
  virsh dumpxml vsf-gpu-$i | grep -A5 hostdev | head -10
done
```

## VirtualBMC Ports (Pending)
- vsf-gpu-1: 6243
- vsf-gpu-2: 6244
- vsf-gpu-3: 6245
- vsf-gpu-4: 6246
- vsf-gpu-5: 6247
- vsf-gpu-6: 6248
- vsf-gpu-7: 6249
- vsf-gpu-8: 6250

## Notes
- GPU passthrough requires IOMMU (verified: 254 groups available)
- All 8 NVIDIA GPUs detected on host (10de:2331 - NVIDIA H100)
- libvirtd became unresponsive during VM start operation
- VMs exist but may need GPU attachment completed after libvirtd restart
