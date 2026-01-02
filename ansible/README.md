# VSF Ansible Playbooks

Ansible playbooks for deploying and managing the Virtual Server Farm K3s cluster.

## Prerequisites

```bash
# Install Ansible
pip install ansible

# Set K3S token (or use default)
export K3S_TOKEN="your-secure-token"

# Ensure SSH access to VMs
ssh-add ~/.ssh/vsf_key
```

## Directory Structure

```
ansible/
├── ansible.cfg           # Ansible configuration
├── inventory/
│   └── vsf.yml          # VSF VM inventory
├── k3s/
│   ├── deploy-control-plane.yml   # Task 105: Deploy K3s HA
│   ├── install-calico.yml         # Task 106: Install CNI
│   ├── join-workers.yml           # Tasks 107-108: Join workers
│   └── join-gpu-workers.yml       # Task 109: Join GPU workers
└── README.md
```

## Playbook Execution Order

### Wave 1: K3s Cluster Setup

```bash
cd ansible/

# 1. Deploy K3s HA control plane (Task 105)
ansible-playbook k3s/deploy-control-plane.yml

# 2. Install Calico CNI (Task 106)
ansible-playbook k3s/install-calico.yml

# 3. Join standard workers (Tasks 107-108)
ansible-playbook k3s/join-workers.yml

# 4. Join GPU workers (Task 109)
ansible-playbook k3s/join-gpu-workers.yml

# 5. Deploy mock GPU exporter (Task 111)
ansible-playbook k3s/deploy-mock-dcgm.yml
```

### Validate Cluster

```bash
# Use the generated kubeconfig
export KUBECONFIG=$(pwd)/kubeconfig-vsf.yaml

# Check nodes
kubectl get nodes -o wide

# Check system pods
kubectl get pods -A
```

## Inventory Groups

| Group | Hosts | Purpose |
|-------|-------|---------|
| `control_plane` | vsf-cp-1, vsf-cp-2, vsf-cp-3 | K3s server nodes (HA) |
| `workers` | vsf-worker-1..10 | Standard worker nodes |
| `gpu_workers` | vsf-gpu-1..8 | GPU worker nodes |
| `all_workers` | workers + gpu_workers | All worker nodes |
| `k3s_cluster` | All K3s nodes | Full cluster |

## Variables

### Cluster Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `k3s_version` | v1.29.0+k3s1 | K3s version to install |
| `k3s_token` | env:K3S_TOKEN | Cluster join token |
| `cluster_cidr` | 10.42.0.0/16 | Pod network CIDR |
| `service_cidr` | 10.43.0.0/16 | Service network CIDR |
| `cluster_dns` | 10.43.0.10 | CoreDNS service IP |

### Node Labels

Control plane nodes get:
- `node-role.kubernetes.io/control-plane=true`
- `vsf/node-type=control-plane`

Standard workers get:
- `node-role.kubernetes.io/worker=true`
- `vsf/node-type=standard`

GPU workers get:
- `node-role.kubernetes.io/worker=true`
- `vsf/node-type=gpu`
- `nvidia.com/gpu.present=true`
- Taint: `nvidia.com/gpu=true:NoSchedule`

## Troubleshooting

### SSH Issues

```bash
# Test connectivity
ansible control_plane -m ping

# Check SSH key
ssh -i ~/.ssh/vsf_key ubuntu@192.168.100.11
```

### K3s Issues

```bash
# Check K3s service
ssh vsf-cp-1 "sudo systemctl status k3s"

# View K3s logs
ssh vsf-cp-1 "sudo journalctl -u k3s -f"

# Reset K3s (destructive)
ssh vsf-cp-1 "sudo /usr/local/bin/k3s-uninstall.sh"
```

### Kubeconfig

```bash
# Regenerate kubeconfig
ansible-playbook k3s/deploy-control-plane.yml --tags kubeconfig

# Manual copy
scp vsf-cp-1:/etc/rancher/k3s/k3s.yaml ./kubeconfig-vsf.yaml
sed -i 's/127.0.0.1/192.168.100.11/' kubeconfig-vsf.yaml
```

## Related Tasks

- Task 105: deploy-control-plane.yml
- Task 106: install-calico.yml
- Task 107-108: join-workers.yml
- Task 109: join-gpu-workers.yml
- Task 111: deploy-mock-dcgm.yml
