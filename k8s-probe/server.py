"""
K8s Probe MCP Server

A FastMCP-based MCP server for Kubernetes cluster optimization.
Provides tools for node control, workload management, and metrics collection.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import (
    ClusterMetricsOutput,
    ConsolidateWorkloadsInput,
    ConsolidateWorkloadsOutput,
    DrainNodeInput,
    DrainNodeOutput,
    ErrorResponse,
    GetNodePowerStateInput,
    GPUWorkloadsOutput,
    NodePowerStateOutput,
    SetNodeLabelsInput,
    SetNodeLabelsOutput,
    SetNodeSchedulableInput,
    SetNodeSchedulableOutput,
    WorkloadDistributionOutput,
    WorkloadInfo,
)
from .schemas import TOOLS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Kubernetes Client Wrapper
# =============================================================================

class KubernetesClient:
    """
    Wrapper for Kubernetes operations using kubectl.
    
    Uses kubectl subprocess calls for simplicity and compatibility.
    Can be replaced with kubernetes Python client for production.
    """
    
    def __init__(self, kubeconfig: str | None = None):
        self.kubeconfig = kubeconfig
    
    async def _run_kubectl(
        self,
        args: list[str],
        timeout: int = 30
    ) -> tuple[str, str, int]:
        """Run kubectl command and return stdout, stderr, returncode."""
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        cmd.extend(args)
        
        logger.debug(f"Running: {' '.join(cmd)}")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return (
                stdout.decode("utf-8"),
                stderr.decode("utf-8"),
                proc.returncode or 0
            )
        except asyncio.TimeoutError:
            return "", "Command timed out", 1
        except Exception as e:
            return "", str(e), 1
    
    async def get_nodes(self) -> list[dict[str, Any]]:
        """Get all nodes with their status."""
        stdout, stderr, rc = await self._run_kubectl([
            "get", "nodes", "-o", "json"
        ])
        if rc != 0:
            raise RuntimeError(f"Failed to get nodes: {stderr}")
        
        data = json.loads(stdout)
        return data.get("items", [])
    
    async def get_pods(self, all_namespaces: bool = True) -> list[dict[str, Any]]:
        """Get all pods."""
        args = ["get", "pods", "-o", "json"]
        if all_namespaces:
            args.append("--all-namespaces")
        
        stdout, stderr, rc = await self._run_kubectl(args)
        if rc != 0:
            raise RuntimeError(f"Failed to get pods: {stderr}")
        
        data = json.loads(stdout)
        return data.get("items", [])
    
    async def cordon_node(self, node_name: str) -> bool:
        """Cordon a node (mark unschedulable)."""
        stdout, stderr, rc = await self._run_kubectl([
            "cordon", node_name
        ])
        return rc == 0
    
    async def uncordon_node(self, node_name: str) -> bool:
        """Uncordon a node (mark schedulable)."""
        stdout, stderr, rc = await self._run_kubectl([
            "uncordon", node_name
        ])
        return rc == 0
    
    async def drain_node(
        self,
        node_name: str,
        timeout: int = 300,
        force: bool = False,
        ignore_daemonsets: bool = True,
        delete_emptydir: bool = False,
        dry_run: bool = False
    ) -> tuple[bool, int, str]:
        """
        Drain a node.
        Returns: (success, pods_evicted, message)
        """
        args = ["drain", node_name, f"--timeout={timeout}s"]
        
        if force:
            args.append("--force")
        if ignore_daemonsets:
            args.append("--ignore-daemonsets")
        if delete_emptydir:
            args.append("--delete-emptydir-data")
        if dry_run:
            args.append("--dry-run=client")
        
        stdout, stderr, rc = await self._run_kubectl(args, timeout=timeout + 30)
        
        # Count evicted pods from output
        pods_evicted = stdout.count("evicting pod")
        
        if rc == 0:
            return True, pods_evicted, "Drain completed successfully"
        else:
            return False, pods_evicted, stderr
    
    async def label_node(
        self,
        node_name: str,
        labels: dict[str, str],
        remove_labels: list[str] | None = None
    ) -> bool:
        """Set or remove labels on a node."""
        args = ["label", "node", node_name, "--overwrite"]
        
        for key, value in labels.items():
            args.append(f"{key}={value}")
        
        for key in (remove_labels or []):
            args.append(f"{key}-")
        
        stdout, stderr, rc = await self._run_kubectl(args)
        return rc == 0


# =============================================================================
# K8s Probe MCP Server
# =============================================================================

class K8sProbeServer:
    """
    K8s Probe MCP Server implementation.
    
    Provides 8 tools for cluster optimization:
    - get_cluster_metrics: Overall cluster status
    - get_node_power_state: Individual node status
    - set_node_schedulable: Cordon/uncordon nodes
    - drain_node: Safely evict pods from node
    - get_workload_distribution: Pod distribution
    - consolidate_workloads: Migrate to fewer nodes
    - get_gpu_workloads: GPU workload info
    - set_node_labels: Apply optimization labels
    """
    
    def __init__(self, kubeconfig: str | None = None):
        self.k8s = KubernetesClient(kubeconfig)
        self.tool_handlers = {
            "get_cluster_metrics": self.get_cluster_metrics,
            "get_node_power_state": self.get_node_power_state,
            "set_node_schedulable": self.set_node_schedulable,
            "drain_node": self.drain_node,
            "get_workload_distribution": self.get_workload_distribution,
            "consolidate_workloads": self.consolidate_workloads,
            "get_gpu_workloads": self.get_gpu_workloads,
            "set_node_labels": self.set_node_labels,
        }
    
    def list_tools(self) -> list[dict[str, Any]]:
        """Return available tools (MCP protocol)."""
        return TOOLS
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool and return results (MCP protocol)."""
        handler = self.tool_handlers.get(tool_name)
        if not handler:
            return ErrorResponse(
                error=f"Unknown tool: {tool_name}",
                code="UNKNOWN_TOOL"
            ).model_dump()
        
        try:
            result = await handler(arguments)
            if isinstance(result, BaseModel):
                return result.model_dump()
            return result
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed: {e}")
            return ErrorResponse(
                error=str(e),
                code="TOOL_EXECUTION_ERROR"
            ).model_dump()
    
    # =========================================================================
    # Tool Implementations
    # =========================================================================
    
    async def get_cluster_metrics(
        self,
        arguments: dict[str, Any]
    ) -> ClusterMetricsOutput:
        """Get overall cluster resource utilization."""
        nodes = await self.k8s.get_nodes()
        pods = await self.k8s.get_pods()
        
        total_nodes = len(nodes)
        ready_nodes = sum(
            1 for n in nodes
            if any(
                c["type"] == "Ready" and c["status"] == "True"
                for c in n.get("status", {}).get("conditions", [])
            )
        )
        schedulable_nodes = sum(
            1 for n in nodes
            if not n.get("spec", {}).get("unschedulable", False)
        )
        
        total_pods = len(pods)
        running_pods = sum(
            1 for p in pods
            if p.get("status", {}).get("phase") == "Running"
        )
        pending_pods = sum(
            1 for p in pods
            if p.get("status", {}).get("phase") == "Pending"
        )
        
        # GPU detection
        gpu_nodes = sum(
            1 for n in nodes
            if "nvidia.com/gpu" in n.get("status", {}).get("capacity", {})
            or any("gpu" in l.lower() for l in n.get("metadata", {}).get("labels", {}).keys())
        )
        gpu_pods = sum(
            1 for p in pods
            if any(
                "nvidia.com/gpu" in c.get("resources", {}).get("requests", {})
                for c in p.get("spec", {}).get("containers", [])
            )
        )
        
        # CPU/Memory utilization would need metrics-server
        # Using placeholder values for now
        return ClusterMetricsOutput(
            total_nodes=total_nodes,
            ready_nodes=ready_nodes,
            schedulable_nodes=schedulable_nodes,
            total_pods=total_pods,
            running_pods=running_pods,
            pending_pods=pending_pods,
            cpu_utilization=0.0,  # Requires metrics-server
            memory_utilization=0.0,  # Requires metrics-server
            gpu_nodes=gpu_nodes,
            gpu_pods=gpu_pods
        )
    
    async def get_node_power_state(
        self,
        arguments: dict[str, Any]
    ) -> NodePowerStateOutput:
        """Get the power/scheduling state of a specific node."""
        params = GetNodePowerStateInput(**arguments)
        
        nodes = await self.k8s.get_nodes()
        node = next(
            (n for n in nodes
             if n.get("metadata", {}).get("name") == params.node_name),
            None
        )
        
        if not node:
            raise ValueError(f"Node not found: {params.node_name}")
        
        conditions = node.get("status", {}).get("conditions", [])
        ready = any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in conditions
        )
        
        schedulable = not node.get("spec", {}).get("unschedulable", False)
        labels = node.get("metadata", {}).get("labels", {})
        
        taints = [
            f"{t['key']}={t.get('value', '')}:{t['effect']}"
            for t in node.get("spec", {}).get("taints", [])
        ]
        
        # Count pods on this node
        pods = await self.k8s.get_pods()
        node_pods = sum(
            1 for p in pods
            if p.get("spec", {}).get("nodeName") == params.node_name
        )
        
        return NodePowerStateOutput(
            node=params.node_name,
            schedulable=schedulable,
            ready=ready,
            pods=node_pods,
            cpu_percent=0.0,  # Requires metrics-server
            memory_percent=0.0,  # Requires metrics-server
            labels=labels,
            taints=taints
        )
    
    async def set_node_schedulable(
        self,
        arguments: dict[str, Any]
    ) -> SetNodeSchedulableOutput:
        """Cordon or uncordon a node."""
        params = SetNodeSchedulableInput(**arguments)
        
        if params.schedulable:
            success = await self.k8s.uncordon_node(params.node_name)
            action = "uncordoned"
        else:
            success = await self.k8s.cordon_node(params.node_name)
            action = "cordoned"
        
        return SetNodeSchedulableOutput(
            node=params.node_name,
            schedulable=params.schedulable,
            success=success,
            message=f"Node {action}" if success else f"Failed to {action[:-2]} node"
        )
    
    async def drain_node(
        self,
        arguments: dict[str, Any]
    ) -> DrainNodeOutput:
        """Safely evict all pods from a node."""
        params = DrainNodeInput(**arguments)
        
        import time
        start = time.time()
        
        success, pods_evicted, message = await self.k8s.drain_node(
            node_name=params.node_name,
            timeout=params.timeout_seconds,
            force=params.force,
            ignore_daemonsets=params.ignore_daemonsets,
            delete_emptydir=params.delete_emptydir_data,
            dry_run=params.dry_run
        )
        
        duration = time.time() - start
        
        return DrainNodeOutput(
            node=params.node_name,
            success=success,
            pods_evicted=pods_evicted,
            pods_failed=0 if success else 1,
            duration_seconds=duration,
            message=message,
            dry_run=params.dry_run
        )
    
    async def get_workload_distribution(
        self,
        arguments: dict[str, Any]
    ) -> WorkloadDistributionOutput:
        """Get the distribution of workloads across all nodes."""
        nodes = await self.k8s.get_nodes()
        pods = await self.k8s.get_pods()
        
        distribution: dict[str, dict] = {}
        for node in nodes:
            node_name = node.get("metadata", {}).get("name", "unknown")
            distribution[node_name] = {
                "pods": 0,
                "gpu_pods": 0,
                "cpu_percent": 0.0,
                "memory_percent": 0.0
            }
        
        total_gpu_pods = 0
        for pod in pods:
            node_name = pod.get("spec", {}).get("nodeName")
            if node_name and node_name in distribution:
                distribution[node_name]["pods"] += 1
                
                # Check for GPU requests
                for container in pod.get("spec", {}).get("containers", []):
                    if "nvidia.com/gpu" in container.get("resources", {}).get("requests", {}):
                        distribution[node_name]["gpu_pods"] += 1
                        total_gpu_pods += 1
                        break
        
        empty_nodes = [n for n, d in distribution.items() if d["pods"] == 0]
        overloaded_nodes = [n for n, d in distribution.items() if d["pods"] > 20]
        
        return WorkloadDistributionOutput(
            nodes=distribution,
            total_pods=len(pods),
            total_gpu_pods=total_gpu_pods,
            empty_nodes=empty_nodes,
            overloaded_nodes=overloaded_nodes
        )
    
    async def consolidate_workloads(
        self,
        arguments: dict[str, Any]
    ) -> ConsolidateWorkloadsOutput:
        """Migrate pods to consolidate workloads onto fewer nodes."""
        params = ConsolidateWorkloadsInput(**arguments)
        
        import time
        start = time.time()
        
        # Get current distribution
        dist = await self.get_workload_distribution({})
        
        # Sort nodes by pod count (ascending) to find emptiest
        sorted_nodes = sorted(
            [(n, d) for n, d in dist.nodes.items() 
             if n not in params.exclude_nodes],
            key=lambda x: x[1]["pods"]
        )
        
        # Determine which nodes to drain
        current_active = len([n for n, d in sorted_nodes if d["pods"] > 0])
        nodes_to_drain = max(0, current_active - params.target_node_count)
        
        source_nodes = []
        pods_moved = 0
        pods_failed = 0
        
        for node_name, node_data in sorted_nodes[:nodes_to_drain]:
            if params.dry_run:
                logger.info(f"[DRY RUN] Would drain node: {node_name}")
                pods_moved += node_data["pods"]
            else:
                # First cordon
                await self.k8s.cordon_node(node_name)
                
                # Then drain
                success, evicted, msg = await self.k8s.drain_node(
                    node_name,
                    timeout=120,
                    ignore_daemonsets=True,
                    force=False
                )
                
                if success:
                    pods_moved += evicted
                else:
                    pods_failed += node_data["pods"]
                    await self.k8s.uncordon_node(node_name)  # Rollback
            
            source_nodes.append(node_name)
        
        # Target nodes are remaining active nodes
        target_nodes = [
            n for n, d in sorted_nodes[nodes_to_drain:]
            if d["pods"] > 0 or params.dry_run
        ][:params.target_node_count]
        
        duration = time.time() - start
        
        return ConsolidateWorkloadsOutput(
            success=pods_failed == 0,
            pods_moved=pods_moved,
            pods_failed=pods_failed,
            source_nodes=source_nodes,
            target_nodes=target_nodes,
            nodes_freed=source_nodes if pods_failed == 0 else [],
            duration_seconds=duration,
            dry_run=params.dry_run,
            message=f"Consolidated from {len(source_nodes)} nodes" if pods_failed == 0 else "Partial consolidation"
        )
    
    async def get_gpu_workloads(
        self,
        arguments: dict[str, Any]
    ) -> GPUWorkloadsOutput:
        """Get information about GPU workloads in the cluster."""
        nodes = await self.k8s.get_nodes()
        pods = await self.k8s.get_pods()
        
        gpu_nodes = sum(
            1 for n in nodes
            if "nvidia.com/gpu" in n.get("status", {}).get("capacity", {})
            or any("gpu" in l.lower() for l in n.get("metadata", {}).get("labels", {}).keys())
        )
        
        workloads: list[WorkloadInfo] = []
        total_allocated = 0
        
        for pod in pods:
            for container in pod.get("spec", {}).get("containers", []):
                gpu_request = container.get("resources", {}).get("requests", {}).get("nvidia.com/gpu")
                if gpu_request:
                    gpu_count = int(gpu_request) if gpu_request else 0
                    total_allocated += gpu_count
                    
                    workloads.append(WorkloadInfo(
                        name=pod.get("metadata", {}).get("name", "unknown"),
                        namespace=pod.get("metadata", {}).get("namespace", "default"),
                        replicas=1,
                        available=1 if pod.get("status", {}).get("phase") == "Running" else 0,
                        node=pod.get("spec", {}).get("nodeName"),
                        gpu_count=gpu_count
                    ))
                    break  # Only count once per pod
        
        # Total available from node capacity
        total_available = sum(
            int(n.get("status", {}).get("capacity", {}).get("nvidia.com/gpu", 0))
            for n in nodes
        )
        
        return GPUWorkloadsOutput(
            gpu_nodes=gpu_nodes,
            gpu_pods=len(workloads),
            total_gpus_allocated=total_allocated,
            total_gpus_available=total_available,
            workloads=workloads
        )
    
    async def set_node_labels(
        self,
        arguments: dict[str, Any]
    ) -> SetNodeLabelsOutput:
        """Set or remove labels on a node."""
        params = SetNodeLabelsInput(**arguments)
        
        success = await self.k8s.label_node(
            node_name=params.node_name,
            labels=params.labels,
            remove_labels=params.remove_labels
        )
        
        return SetNodeLabelsOutput(
            node=params.node_name,
            labels_set=params.labels if success else {},
            labels_removed=params.remove_labels if success else [],
            success=success,
            message="Labels updated" if success else "Failed to update labels"
        )


# =============================================================================
# Main Entry Point
# =============================================================================

def create_server(kubeconfig: str | None = None) -> K8sProbeServer:
    """Create a K8s Probe MCP server instance."""
    return K8sProbeServer(kubeconfig)


if __name__ == "__main__":
    import sys
    
    # Simple test
    async def main():
        server = create_server()
        
        print("Available tools:")
        for tool in server.list_tools():
            print(f"  - {tool['name']}: {tool['description']}")
        
        print("\nTesting get_cluster_metrics...")
        result = await server.call_tool("get_cluster_metrics", {})
        print(f"  Result: {result}")
    
    asyncio.run(main())
