# Task 98: Control Plane VMs - Deployment Report

## Status: BLOCKED

**Track**: A  
**Task ID**: 98  
**Date**: 2026-01-01  
**Agent**: Track A (claimed via parallel planning group)

## Summary

Attempted deployment of 3 control plane VMs (vsf-cp-1, vsf-cp-2, vsf-cp-3) for the Virtual Server Farm.

## Resources Created

✅ **Terraform Configuration Fixed**:
- Removed Azure backend, switched to local state
- Fixed duplicate `required_providers` blocks
- Fixed variable name mismatches
- Removed broken template references
- Updated to use `default` storage pool

✅ **Volumes Created**:
- `vsf-ubuntu-22.04-base.qcow2` - Base Ubuntu 22.04 image
- `vsf-cp-1.qcow2` - Control plane VM 1 disk (100GB)
- `vsf-cp-2.qcow2` - Control plane VM 2 disk (100GB)
- `vsf-cp-3.qcow2` - Control plane VM 3 disk (100GB)
- `vsf-cp-{1,2,3}-init.iso` - Cloud-init ISOs

✅ **Cloud-Init Configuration**:
- Hostnames: vsf-cp-1, vsf-cp-2, vsf-cp-3
- SSH key configured for user `ubuntu`
- QEMU guest agent enabled
- Packages: htop, vim

❌ **VM Domains**: Failed to start due to permission denied

## Blocking Issue

All VMs fail to start with the error:
```
Could not open '/var/lib/libvirt/images/vsf-ubuntu-22.04-base.qcow2': Permission denied
```

This is a **system-wide libvirt/AppArmor issue** affecting all VMs (including existing ones like `f10-smoke-test-vm`).

### Root Cause
The QEMU process cannot access disk image files due to:
1. AppArmor profile restrictions on libvirt
2. File ownership/permission issues in `/var/lib/libvirt/images/`

### Required Fix (needs sudo)
```bash
# Option 1: Adjust AppArmor profile
sudo aa-complain /usr/sbin/libvirtd

# Option 2: Fix file permissions
sudo chown -R libvirt-qemu:kvm /var/lib/libvirt/images/
sudo chmod -R 775 /var/lib/libvirt/images/

# Option 3: Update /etc/libvirt/qemu.conf
# Set: security_driver = "none"
# Then: sudo systemctl restart libvirtd
```

## VM Specifications (When Fixed)

| VM | vCPUs | Memory | Disk | IP Range |
|----|-------|--------|------|----------|
| vsf-cp-1 | 8 | 32GB | 100GB | 10.100.0.x |
| vsf-cp-2 | 8 | 32GB | 100GB | 10.100.0.x |
| vsf-cp-3 | 8 | 32GB | 100GB | 10.100.0.x |

## Network

- **Network Name**: vsf-cluster
- **CIDR**: 10.100.0.0/24
- **Mode**: NAT with DHCP

## Files Modified

1. `terraform/backend.tf` - Switched to local backend
2. `terraform/main.tf` - Simplified, uses default pool
3. `terraform/variables.tf` - Fixed variable names
4. `terraform/outputs.tf` - Removed undefined references
5. `terraform/cloud-init/user-data.tftpl` - Added SSH key and hostname

## Next Steps

1. **BLOCKER**: Fix system-wide libvirt permission issue (requires sudo)
2. After fix, run: `terraform apply -target=libvirt_domain.control_plane`
3. Verify with: `virsh list --all | grep vsf-cp`

## Verification Commands (Post-Fix)

```bash
# List VMs
virsh list --all | grep vsf-cp

# Check IP addresses
virsh domifaddr vsf-cp-1 --source agent

# SSH into VM
ssh ubuntu@<ip-address>
```
