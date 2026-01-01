# GPU Passthrough Configuration for GPU Worker VMs
# Each GPU worker gets one dedicated GPU

locals {
  # Map of GPU worker index to PCI address (domain:bus:slot.function)
  gpu_pci_addresses = {
    0 = { domain = "0000", bus = "16", slot = "00", function = "0" }  # vsf-gpu-1
    1 = { domain = "0000", bus = "40", slot = "00", function = "0" }  # vsf-gpu-2
    2 = { domain = "0000", bus = "94", slot = "00", function = "0" }  # vsf-gpu-3
    3 = { domain = "0000", bus = "be", slot = "00", function = "0" }  # vsf-gpu-4
    4 = { domain = "0001", bus = "16", slot = "00", function = "0" }  # vsf-gpu-5
    5 = { domain = "0001", bus = "6a", slot = "00", function = "0" }  # vsf-gpu-6
    6 = { domain = "0001", bus = "94", slot = "00", function = "0" }  # vsf-gpu-7
    7 = { domain = "0001", bus = "be", slot = "00", function = "0" }  # vsf-gpu-8
  }
}
