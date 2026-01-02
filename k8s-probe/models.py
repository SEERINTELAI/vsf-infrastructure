"""
K8s Probe MCP - Pydantic Models

Defines input/output schemas for all K8s Probe MCP tools.
"""

from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# Common Models
# =============================================================================

class NodeInfo(BaseModel):
    """Basic node information."""
    name: str
    schedulable: bool
    ready: bool
    pods: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    labels: dict[str, str] = Field(default_factory=dict)


class PodInfo(BaseModel):
    """Basic pod information."""
    name: str
    namespace: str
    node: str
    status: str
    cpu_request: Optional[str] = None
    memory_request: Optional[str] = None
    gpu_count: int = 0


class WorkloadInfo(BaseModel):
    """Workload (Deployment/StatefulSet) information."""
    name: str
    namespace: str
    replicas: int
    available: int
    node: Optional[str] = None
    gpu_count: int = 0


# =============================================================================
# Tool Input Models
# =============================================================================

class GetNodePowerStateInput(BaseModel):
    """Input for get_node_power_state tool."""
    node_name: str = Field(..., description="Name of the node to query")


class SetNodeSchedulableInput(BaseModel):
    """Input for set_node_schedulable tool (cordon/uncordon)."""
    node_name: str = Field(..., description="Name of the node to modify")
    schedulable: bool = Field(..., description="True to uncordon, False to cordon")


class DrainNodeInput(BaseModel):
    """Input for drain_node tool."""
    node_name: str = Field(..., description="Name of the node to drain")
    timeout_seconds: int = Field(300, description="Timeout for drain operation")
    force: bool = Field(False, description="Force drain even with local storage")
    ignore_daemonsets: bool = Field(True, description="Ignore DaemonSet pods")
    delete_emptydir_data: bool = Field(False, description="Delete emptyDir data")
    respect_pdb: bool = Field(True, description="Respect PodDisruptionBudgets")
    dry_run: bool = Field(False, description="Only simulate, don't execute")


class ConsolidateWorkloadsInput(BaseModel):
    """Input for consolidate_workloads tool."""
    target_node_count: int = Field(..., description="Target number of active nodes")
    exclude_namespaces: list[str] = Field(
        default_factory=lambda: ["kube-system", "calico-system"],
        description="Namespaces to exclude from consolidation"
    )
    exclude_nodes: list[str] = Field(
        default_factory=list,
        description="Nodes to exclude from consolidation"
    )
    respect_pdb: bool = Field(True, description="Respect PodDisruptionBudgets")
    dry_run: bool = Field(False, description="Only simulate, don't execute")


class SetNodeLabelsInput(BaseModel):
    """Input for set_node_labels tool."""
    node_name: str = Field(..., description="Name of the node to label")
    labels: dict[str, str] = Field(..., description="Labels to set on the node")
    remove_labels: list[str] = Field(
        default_factory=list,
        description="Label keys to remove from the node"
    )


# =============================================================================
# Tool Output Models
# =============================================================================

class ClusterMetricsOutput(BaseModel):
    """Output for get_cluster_metrics tool."""
    total_nodes: int
    ready_nodes: int
    schedulable_nodes: int
    total_pods: int
    running_pods: int
    pending_pods: int
    cpu_utilization: float
    memory_utilization: float
    gpu_nodes: int = 0
    gpu_pods: int = 0


class NodePowerStateOutput(BaseModel):
    """Output for get_node_power_state tool."""
    node: str
    schedulable: bool
    ready: bool
    pods: int
    cpu_percent: float
    memory_percent: float
    labels: dict[str, str] = Field(default_factory=dict)
    taints: list[str] = Field(default_factory=list)


class SetNodeSchedulableOutput(BaseModel):
    """Output for set_node_schedulable tool."""
    node: str
    schedulable: bool
    success: bool
    message: str = ""


class DrainNodeOutput(BaseModel):
    """Output for drain_node tool."""
    node: str
    success: bool
    pods_evicted: int
    pods_failed: int = 0
    duration_seconds: float
    message: str = ""
    dry_run: bool = False


class WorkloadDistributionOutput(BaseModel):
    """Output for get_workload_distribution tool."""
    nodes: dict[str, dict]  # node_name -> {pods, gpu_pods, cpu_percent, memory_percent}
    total_pods: int
    total_gpu_pods: int = 0
    empty_nodes: list[str] = Field(default_factory=list)
    overloaded_nodes: list[str] = Field(default_factory=list)


class ConsolidateWorkloadsOutput(BaseModel):
    """Output for consolidate_workloads tool."""
    success: bool
    pods_moved: int
    pods_failed: int = 0
    source_nodes: list[str]
    target_nodes: list[str]
    nodes_freed: list[str] = Field(default_factory=list)
    duration_seconds: float
    dry_run: bool = False
    message: str = ""


class GPUWorkloadsOutput(BaseModel):
    """Output for get_gpu_workloads tool."""
    gpu_nodes: int
    gpu_pods: int
    total_gpus_allocated: int = 0
    total_gpus_available: int = 0
    workloads: list[WorkloadInfo]


class SetNodeLabelsOutput(BaseModel):
    """Output for set_node_labels tool."""
    node: str
    labels_set: dict[str, str]
    labels_removed: list[str]
    success: bool
    message: str = ""


# =============================================================================
# Error Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    code: str = "UNKNOWN_ERROR"
    details: Optional[dict] = None
