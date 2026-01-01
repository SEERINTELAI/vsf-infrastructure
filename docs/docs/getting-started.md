# Getting Started

## Prerequisites

- Terraform >= 1.5.0
- Python >= 3.11
- libvirt with qemu-kvm on target host

## Installation

```bash
pip install -r requirements.txt
cd terraform && terraform init
terraform validate
```

## Host Preparation

### Enable IOMMU
Add to /etc/default/grub: `GRUB_CMDLINE_LINUX="intel_iommu=on iommu=pt"`

### Configure HugePages
Add to /etc/sysctl.conf: `vm.nr_hugepages = 900`

### Install Packages
```bash
sudo apt install -y qemu-kvm libvirt-daemon virtinst openvswitch-switch
```

## Running Tests
```bash
pytest tests/ -v
```
