# K8s Probe MCP Server

A Model Context Protocol (MCP) server for Kubernetes cluster optimization in the Virtual Server Farm (VSF).

## Overview

The K8s Probe provides cluster-level optimization controls that complement the per-node System Probe. It enables workload consolidation, node power management, and GPU workload scheduling.

## Architecture

```
┌─────────────────────────────────────────────┐
│              AgentOne                       │
│         (Optimization Controller)           │
└────────────────────┬────────────────────────┘
                     │ MCP
                     ▼
┌─────────────────────────────────────────────┐
│              K8s Probe MCP                  │
│  ┌─────────────────────────────────────┐   │
│  │ Tools:                               │   │
│  │  • get_cluster_metrics              │   │
│  │  • get_node_power_state             │   │
│  │  • set_node_schedulable             │   │
│  │  • drain_node                       │   │
│  │  • get_workload_distribution        │   │
│  │  • consolidate_workloads            │   │
│  │  • get_gpu_workloads               │   │
│  │  • set_node_labels                  │   │
│  └─────────────────────────────────────┘   │
└────────────────────┬────────────────────────┘
                     │ kubectl
                     ▼
┌─────────────────────────────────────────────┐
│           K3s API Server                    │
│         (VSF Control Plane)                 │
└─────────────────────────────────────────────┘
```

## Tools

### Metrics Tools

#### `get_cluster_metrics`
Get overall cluster resource utilization and node status.

**Input:** None

**Output:**
```json
{
  "total_nodes": 21,
  "ready_nodes": 21,
  "schedulable_nodes": 18,
  "total_pods": 50,
  "running_pods": 48,
  "pending_pods": 2,
  "cpu_utilization": 45.5,
  "memory_utilization": 62.3,
  "gpu_nodes": 8,
  "gpu_pods": 12
}
```

### Node Control Tools

#### `get_node_power_state`
Get the power/scheduling state of a specific node.

**Input:**
```json
{
  "node_name": "vsf-worker-1"
}
```

**Output:**
```json
{
  "node": "vsf-worker-1",
  "schedulable": true,
  "ready": true,
  "pods": 5,
  "cpu_percent": 30.0,
  "memory_percent": 40.0,
  "labels": {"node-role.kubernetes.io/worker": ""},
  "taints": []
}
```

#### `set_node_schedulable`
Cordon or uncordon a node (set schedulable state).

**Input:**
```json
{
  "node_name": "vsf-worker-5",
  "schedulable": false
}
```

#### `drain_node`
Safely evict all pods from a node for maintenance or power-down.

**Input:**
```json
{
  "node_name": "vsf-worker-5",
  "timeout_seconds": 300,
  "force": false,
  "ignore_daemonsets": true,
  "respect_pdb": true,
  "dry_run": false
}
```

#### `set_node_labels`
Set or remove labels on a node for optimization purposes.

**Input:**
```json
{
  "node_name": "vsf-worker-1",
  "labels": {"vsf/power-state": "active"},
  "remove_labels": ["old-label"]
}
```

### Workload Tools

#### `get_workload_distribution`
Get the distribution of workloads across all nodes.

**Output:**
```json
{
  "nodes": {
    "vsf-worker-1": {"pods": 10, "gpu_pods": 0, "cpu_percent": 45.0},
    "vsf-worker-2": {"pods": 8, "gpu_pods": 0, "cpu_percent": 38.0},
    "vsf-gpu-1": {"pods": 3, "gpu_pods": 2, "cpu_percent": 60.0}
  },
  "total_pods": 21,
  "total_gpu_pods": 2,
  "empty_nodes": ["vsf-worker-8", "vsf-worker-9"],
  "overloaded_nodes": []
}
```

#### `consolidate_workloads`
Migrate pods to consolidate workloads onto fewer nodes for power savings.

**Input:**
```json
{
  "target_node_count": 5,
  "exclude_namespaces": ["kube-system", "calico-system"],
  "exclude_nodes": ["vsf-cp-1", "vsf-cp-2", "vsf-cp-3"],
  "respect_pdb": true,
  "dry_run": true
}
```

**Output:**
```json
{
  "success": true,
  "pods_moved": 15,
  "pods_failed": 0,
  "source_nodes": ["vsf-worker-5", "vsf-worker-6"],
  "target_nodes": ["vsf-worker-1", "vsf-worker-2"],
  "nodes_freed": ["vsf-worker-5", "vsf-worker-6"],
  "duration_seconds": 120.5,
  "dry_run": true
}
```

#### `get_gpu_workloads`
Get information about GPU workloads in the cluster.

**Output:**
```json
{
  "gpu_nodes": 8,
  "gpu_pods": 12,
  "total_gpus_allocated": 10,
  "total_gpus_available": 16,
  "workloads": [
    {"name": "ml-training-1", "namespace": "ml", "node": "vsf-gpu-1", "gpu_count": 1}
  ]
}
```

## Usage

### As a Module

```python
import asyncio
from k8s_probe.server import create_server

async def main():
    server = create_server(kubeconfig="/path/to/kubeconfig")
    
    # List available tools
    tools = server.list_tools()
    
    # Call a tool
    result = await server.call_tool("get_cluster_metrics", {})
    print(result)

asyncio.run(main())
```

### As an MCP Server

```bash
# Start the MCP server (requires FastMCP integration)
python -m k8s_probe --port 8080
```

## RBAC Requirements

The K8s Probe requires the following Kubernetes RBAC permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: k8s-probe
rules:
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "delete", "evict"]
  - apiGroups: [""]
    resources: ["pods/eviction"]
    verbs: ["create"]
```

## Testing

```bash
pytest tests/test_k8s_probe.py -v

# Run specific categories
pytest tests/test_k8s_probe.py -v -m node_control
pytest tests/test_k8s_probe.py -v -m workload
```

## Files

- `__init__.py` - Package init
- `server.py` - Main MCP server implementation
- `models.py` - Pydantic input/output models
- `schemas.py` - MCP tool schemas
- `tools/` - Organized tool implementations (future)

## Dependencies

- Python 3.11+
- pydantic
- kubectl (accessible in PATH)
- Kubernetes cluster with RBAC permissions
