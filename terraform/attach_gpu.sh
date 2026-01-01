#!/bin/bash
# Script to attach GPU to VM
# Usage: attach_gpu.sh <vm_index>

VM_INDEX=$1
VM_NAME="vsf-gpu-$((VM_INDEX + 1))"

# GPU PCI addresses array (indexed by VM number - 1)
declare -A GPU_ADDRS=(
  [0]="0000:16:00.0"
  [1]="0000:40:00.0"
  [2]="0000:94:00.0"
  [3]="0000:be:00.0"
  [4]="0001:16:00.0"
  [5]="0001:6a:00.0"
  [6]="0001:94:00.0"
  [7]="0001:be:00.0"
)

GPU_ADDR="${GPU_ADDRS[$VM_INDEX]}"

# Parse PCI address
DOMAIN=$(echo $GPU_ADDR | cut -d: -f1)
BUS=$(echo $GPU_ADDR | cut -d: -f2)
SLOT_FUNC=$(echo $GPU_ADDR | cut -d: -f3)
SLOT=$(echo $SLOT_FUNC | cut -d. -f1)
FUNC=$(echo $SLOT_FUNC | cut -d. -f2)

# Create hostdev XML
cat > /tmp/gpu-${VM_INDEX}.xml << XMLEOF
<hostdev mode='subsystem' type='pci' managed='yes'>
  <source>
    <address domain='0x$DOMAIN' bus='0x$BUS' slot='0x$SLOT' function='0x$FUNC'/>
  </source>
</hostdev>
XMLEOF

echo "Attaching GPU $GPU_ADDR to $VM_NAME"

# Check if VM exists
if ! virsh dominfo "$VM_NAME" > /dev/null 2>&1; then
    echo "VM $VM_NAME not found, skipping"
    exit 0
fi

# Check if GPU already attached
if virsh dumpxml "$VM_NAME" | grep -q "$BUS.*$SLOT.*$FUNC"; then
    echo "GPU already attached to $VM_NAME"
    exit 0
fi

# Get VM state
VM_STATE=$(virsh domstate "$VM_NAME" 2>/dev/null)

# If running, shut it down first
if [ "$VM_STATE" = "running" ]; then
    echo "Shutting down $VM_NAME..."
    virsh shutdown "$VM_NAME"
    sleep 10
fi

# Attach device persistently
echo "Attaching GPU device..."
virsh attach-device "$VM_NAME" /tmp/gpu-${VM_INDEX}.xml --config

# Start VM
echo "Starting $VM_NAME..."
virsh start "$VM_NAME" || true

echo "Done attaching GPU $GPU_ADDR to $VM_NAME"
