# Architecture Overview

## Design Goals

1. Reproducibility: Identical test environments
2. Scalability: Easy to add/remove nodes
3. Isolation: Tests don't affect each other
4. Observability: Comprehensive monitoring

## VM Topology

- Control Plane (3 VMs): K8s masters with etcd
- Standard Workers (10 VMs): General workloads
- GPU Workers (8 VMs): ML/GPU workloads with passthrough
- Infrastructure (3 VMs): Prometheus, DNS, Storage

## Networking

| VLAN | CIDR | Purpose |
|------|------|---------|
| 100 | 10.100.0.0/24 | Cluster network |
| 200 | 10.200.0.0/24 | Storage network |

## Key Technologies

- KVM/QEMU + libvirt: Hypervisor
- Terraform + libvirt provider: IaC
- Open vSwitch: Virtual networking
- HugePages: Memory optimization
- IOMMU/VFIO: GPU passthrough
