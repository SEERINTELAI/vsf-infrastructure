"""
Metrics Aggregator

Collects and aggregates metrics from all 23 probes in the VSF cluster.
Provides unified view of cluster state for optimization decisions.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .router import ProbeRouter, ProbeType, MCPCallResult

logger = logging.getLogger(__name__)


@dataclass
class NodeMetrics:
    """Metrics from a single node/probe."""
    probe_id: str
    hostname: str
    probe_type: str
    timestamp: datetime
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    power_watts: float | None = None
    additional: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ClusterMetrics:
    """Aggregated metrics from K8s cluster probe."""
    timestamp: datetime
    total_nodes: int = 0
    ready_nodes: int = 0
    schedulable_nodes: int = 0
    total_pods: int = 0
    running_pods: int = 0
    pending_pods: int = 0
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    gpu_nodes: int = 0
    gpu_pods: int = 0


@dataclass
class AggregatedMetrics:
    """Complete aggregated view of all metrics."""
    timestamp: datetime
    cluster: ClusterMetrics | None = None
    nodes: list[NodeMetrics] = field(default_factory=list)
    
    # Computed aggregates
    total_probes: int = 0
    healthy_probes: int = 0
    avg_cpu_percent: float = 0.0
    avg_memory_percent: float = 0.0
    total_power_watts: float | None = None
    
    def compute_aggregates(self):
        """Compute aggregate values from node metrics."""
        if not self.nodes:
            return
        
        self.total_probes = len(self.nodes) + (1 if self.cluster else 0)
        self.healthy_probes = sum(1 for n in self.nodes if n.error is None)
        
        valid_nodes = [n for n in self.nodes if n.error is None]
        if valid_nodes:
            self.avg_cpu_percent = sum(n.cpu_percent for n in valid_nodes) / len(valid_nodes)
            self.avg_memory_percent = sum(n.memory_percent for n in valid_nodes) / len(valid_nodes)
            
            power_nodes = [n for n in valid_nodes if n.power_watts is not None]
            if power_nodes:
                self.total_power_watts = sum(n.power_watts for n in power_nodes)


class MetricsAggregator:
    """
    Aggregates metrics from all probes in the VSF cluster.
    
    Responsibilities:
    - Collect metrics from K8s probe
    - Collect metrics from all VM probes
    - Collect metrics from host probe
    - Aggregate and cache results
    - Provide unified view for controller
    """
    
    def __init__(
        self,
        router: ProbeRouter,
        cache_ttl_seconds: int = 30
    ):
        self.router = router
        self.cache_ttl = cache_ttl_seconds
        self._cache: AggregatedMetrics | None = None
        self._cache_time: datetime | None = None
    
    def _cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache is None or self._cache_time is None:
            return False
        
        age = (datetime.now() - self._cache_time).total_seconds()
        return age < self.cache_ttl
    
    async def collect_cluster_metrics(self) -> ClusterMetrics | None:
        """Collect metrics from K8s probe."""
        k8s_probes = self.router.list_probes(probe_type=ProbeType.K8S)
        
        if not k8s_probes:
            logger.warning("No K8s probe registered")
            return None
        
        probe = k8s_probes[0]
        result = await self.router.call_tool(
            probe.probe_id,
            "get_cluster_metrics",
            {}
        )
        
        if not result.success:
            logger.error(f"Failed to get cluster metrics: {result.error}")
            return None
        
        data = result.result or {}
        return ClusterMetrics(
            timestamp=datetime.now(),
            total_nodes=data.get("total_nodes", 0),
            ready_nodes=data.get("ready_nodes", 0),
            schedulable_nodes=data.get("schedulable_nodes", 0),
            total_pods=data.get("total_pods", 0),
            running_pods=data.get("running_pods", 0),
            pending_pods=data.get("pending_pods", 0),
            cpu_utilization=data.get("cpu_utilization", 0.0),
            memory_utilization=data.get("memory_utilization", 0.0),
            gpu_nodes=data.get("gpu_nodes", 0),
            gpu_pods=data.get("gpu_pods", 0)
        )
    
    async def collect_node_metrics(
        self,
        probe_types: list[ProbeType] | None = None
    ) -> list[NodeMetrics]:
        """Collect metrics from all node probes."""
        if probe_types is None:
            probe_types = [ProbeType.VM_SYSTEM, ProbeType.HOST_SYSTEM]
        
        all_probes = []
        for pt in probe_types:
            all_probes.extend(self.router.list_probes(probe_type=pt))
        
        # Collect in parallel
        tasks = []
        for probe in all_probes:
            tasks.append(self._collect_single_node(probe))
        
        return await asyncio.gather(*tasks)
    
    async def _collect_single_node(self, probe) -> NodeMetrics:
        """Collect metrics from a single node probe."""
        result = await self.router.call_tool(
            probe.probe_id,
            "system_info",
            {}
        )
        
        if not result.success:
            return NodeMetrics(
                probe_id=probe.probe_id,
                hostname=probe.hostname,
                probe_type=probe.probe_type.value,
                timestamp=datetime.now(),
                error=result.error
            )
        
        data = result.result or {}
        return NodeMetrics(
            probe_id=probe.probe_id,
            hostname=probe.hostname,
            probe_type=probe.probe_type.value,
            timestamp=datetime.now(),
            cpu_percent=data.get("cpu_percent", 0.0),
            memory_percent=data.get("memory_percent", 0.0),
            power_watts=data.get("power_watts"),
            additional={
                k: v for k, v in data.items()
                if k not in ["cpu_percent", "memory_percent", "power_watts", "hostname"]
            }
        )
    
    async def collect_all(self, force_refresh: bool = False) -> AggregatedMetrics:
        """
        Collect all metrics from all probes.
        
        Args:
            force_refresh: Bypass cache and collect fresh data
            
        Returns:
            AggregatedMetrics with complete cluster view
        """
        # Check cache
        if not force_refresh and self._cache_valid():
            return self._cache
        
        logger.info("Collecting metrics from all probes...")
        
        # Collect in parallel
        cluster_task = self.collect_cluster_metrics()
        nodes_task = self.collect_node_metrics()
        
        cluster, nodes = await asyncio.gather(cluster_task, nodes_task)
        
        # Build aggregated view
        metrics = AggregatedMetrics(
            timestamp=datetime.now(),
            cluster=cluster,
            nodes=nodes
        )
        metrics.compute_aggregates()
        
        # Update cache
        self._cache = metrics
        self._cache_time = datetime.now()
        
        logger.info(
            f"Collected metrics from {metrics.total_probes} probes "
            f"({metrics.healthy_probes} healthy)"
        )
        
        return metrics
    
    async def get_summary(self) -> dict[str, Any]:
        """Get a summary of current cluster state."""
        metrics = await self.collect_all()
        
        summary = {
            "timestamp": metrics.timestamp.isoformat(),
            "total_probes": metrics.total_probes,
            "healthy_probes": metrics.healthy_probes,
            "avg_cpu_percent": round(metrics.avg_cpu_percent, 2),
            "avg_memory_percent": round(metrics.avg_memory_percent, 2),
        }
        
        if metrics.total_power_watts is not None:
            summary["total_power_watts"] = round(metrics.total_power_watts, 2)
        
        if metrics.cluster:
            summary["cluster"] = {
                "total_nodes": metrics.cluster.total_nodes,
                "ready_nodes": metrics.cluster.ready_nodes,
                "total_pods": metrics.cluster.total_pods,
                "running_pods": metrics.cluster.running_pods,
            }
        
        return summary
    
    async def get_workload_distribution(self) -> dict[str, Any]:
        """Get workload distribution from K8s probe."""
        k8s_probes = self.router.list_probes(probe_type=ProbeType.K8S)
        
        if not k8s_probes:
            return {"error": "No K8s probe registered"}
        
        result = await self.router.call_tool(
            k8s_probes[0].probe_id,
            "get_workload_distribution",
            {}
        )
        
        if result.success:
            return result.result or {}
        else:
            return {"error": result.error}
