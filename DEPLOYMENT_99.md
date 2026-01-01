# Task 99: Standard Worker VMs Deployment

## Status: Partial - VMs Defined, Pending Storage Permission Fix

## VMs Created (Definitions)
All 10 worker VMs have been defined in libvirt:
- vsf-worker-1 through vsf-worker-10
- IPs: 10.0.0.20 - 10.0.0.29

## Terraform Module Fix Applied
Fixed `terraform/modules/vm/main.tf` to remove unsupported blocks:
- Removed `memory { hugepages = ... }` block (not supported by libvirt provider 0.7.x)
- Removed `hostdev` dynamic block (GPU passthrough requires XML workaround)

## Storage Volumes Created
All volumes exist in `vsf-storage` pool:
- 10x base images (downloaded from Ubuntu cloud)
- 10x root volumes (200GB each)
- 10x cloud-init ISOs

## Blocking Issue: Storage Permissions
VMs cannot start due to QEMU permission denied on storage directory:
```
Could not open '/var/lib/libvirt/vsf-images/vsf-worker-X-base.qcow2': Permission denied
```

### Root Cause
The `vsf-storage` pool directory `/var/lib/libvirt/vsf-images` is owned by `root:root` with mode `0711`.
QEMU runs as `libvirt-qemu:kvm` and cannot read the disk images.

### Required Fix (needs sudo)
```bash
sudo chown -R libvirt-qemu:kvm /var/lib/libvirt/vsf-images
sudo chmod -R 775 /var/lib/libvirt/vsf-images
```

Alternatively, modify `/etc/libvirt/qemu.conf`:
```
security_driver = "none"
```

## VirtualBMC Ports
- vsf-worker-1: 6233
- vsf-worker-2: 6234
- vsf-worker-3: 6235
- vsf-worker-4: 6236
- vsf-worker-5: 6237
- vsf-worker-6: 6238
- vsf-worker-7: 6239
- vsf-worker-8: 6240
- vsf-worker-9: 6241
- vsf-worker-10: 6242

## Next Steps
1. Run the sudo commands above to fix storage permissions
2. Start VMs: `for i in {1..10}; do virsh start vsf-worker-$i; done`
3. Verify with: `virsh list --all | grep vsf-worker`

## Agent: Track B (Task 99)
Completed: 2026-01-01
