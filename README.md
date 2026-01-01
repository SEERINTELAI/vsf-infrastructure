# VSF Infrastructure

Terraform infrastructure-as-code for the Virtual Server Farm (VSF) on Bizon1.

## Overview

This repository contains:
- **Terraform configurations** for deploying 24-node virtualized server farm
- **Libvirt/QEMU/KVM** VM provisioning with GPU passthrough support
- **pytest test framework** for infrastructure validation
- **MkDocs documentation** for deployment guides

## Architecture

```
Bizon1 Host (1TB RAM, 200 vCPU, 8 GPU)
├── Control Plane (3 VMs)
│   ├── k8s-master-1 (8 vCPU, 32GB RAM)
│   ├── k8s-master-2 (8 vCPU, 32GB RAM)
│   └── k8s-master-3 (8 vCPU, 32GB RAM)
├── Worker Nodes (10 VMs)
│   └── worker-1..10 (4 vCPU, 16GB RAM each)
├── GPU Workers (8 VMs)
│   └── gpu-worker-1..8 (8 vCPU, 64GB RAM, 1 GPU each)
└── Infrastructure (3 VMs)
    ├── prometheus (4 vCPU, 16GB RAM)
    ├── dns (2 vCPU, 4GB RAM)
    └── storage (4 vCPU, 32GB RAM)
```

## Quick Start

### 1. Clone Repository

```bash
git clone git@github.com:SEERINTELAI/vsf-infrastructure.git
cd vsf-infrastructure
```

### 2. Configure Variables

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars
```

### 3. Deploy

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

## Directory Structure

```
vsf-infrastructure/
├── terraform/           # Terraform configurations
├── tests/               # pytest test suite
├── docs/                # MkDocs documentation
└── .github/workflows/   # CI/CD pipeline
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Documentation

```bash
pip install mkdocs mkdocs-material
mkdocs serve
# Open http://localhost:8000
```

## Feature Context

Supports **F10: Virtual Server Farm** - development infrastructure for energy optimization research.

## License

Proprietary - SEERINTELAI
