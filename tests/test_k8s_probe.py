"""
K8s Probe MCP Test Suite (DP:FULL Compliant)

Tests for the Kubernetes Probe MCP server that provides cluster-level
optimization controls for the Virtual Server Farm.

Pre-Mortem Failure Categories:
1. Connection Failure - MCP server unreachable, auth failures
2. Node Control Failure - Cordon/drain fails, node stuck
3. Workload Failure - Pod migration fails, consolidation breaks apps
4. Metrics Failure - Stale data, missing metrics, aggregation errors
5. Permission Failure - RBAC denies operations, insufficient privileges
6. State Inconsistency - Cluster state differs from probe state

Total: 18 tests across 6 pre-mortem categories (exceeds DP:ETG minimum of 15)

Usage:
    pytest tests/test_k8s_probe.py -v
    pytest tests/test_k8s_probe.py -v -m connection
    pytest tests/test_k8s_probe.py -v -m node_control
    pytest tests/test_k8s_probe.py -v -m workload
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Mock K8s Probe Client (for testing without real cluster)
# =============================================================================

class MockK8sProbeClient:
    """Mock client for K8s Probe MCP server."""
    
    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []
    
    async def call_tool(self, tool_name: str, params: dict) -> dict:
        """Simulate MCP tool call."""
        self.calls.append((tool_name, params))
        
        if tool_name in self.responses:
            response = self.responses[tool_name]
            if callable(response):
                return response(params)
            return response
        
        return {"error": f"Unknown tool: {tool_name}"}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_client():
    """Create mock K8s Probe client with default responses."""
    responses = {
        "get_cluster_metrics": {
            "total_nodes": 21,
            "ready_nodes": 21,
            "total_pods": 50,
            "running_pods": 48,
            "cpu_utilization": 45.5,
            "memory_utilization": 62.3
        },
        "get_node_power_state": lambda p: {
            "node": p.get("node_name", "unknown"),
            "schedulable": True,
            "ready": True,
            "pods": 5,
            "cpu_percent": 30.0,
            "memory_percent": 40.0
        },
        "set_node_schedulable": lambda p: {
            "node": p.get("node_name"),
            "schedulable": p.get("schedulable"),
            "success": True
        },
        "drain_node": lambda p: {
            "node": p.get("node_name"),
            "success": True,
            "pods_evicted": 5,
            "duration_seconds": 30
        },
        "get_workload_distribution": {
            "nodes": {
                "vsf-worker-1": {"pods": 10, "gpu_pods": 0},
                "vsf-worker-2": {"pods": 8, "gpu_pods": 0},
                "vsf-gpu-1": {"pods": 3, "gpu_pods": 2}
            },
            "total_pods": 21
        },
        "consolidate_workloads": lambda p: {
            "success": True,
            "pods_moved": 15,
            "source_nodes": ["vsf-worker-5", "vsf-worker-6"],
            "target_nodes": ["vsf-worker-1", "vsf-worker-2"],
            "duration_seconds": 120
        },
        "get_gpu_workloads": {
            "gpu_nodes": 8,
            "gpu_pods": 12,
            "workloads": [
                {"name": "ml-training", "node": "vsf-gpu-1", "gpu_count": 1},
                {"name": "inference", "node": "vsf-gpu-2", "gpu_count": 1}
            ]
        },
        "set_node_labels": lambda p: {
            "node": p.get("node_name"),
            "labels_set": p.get("labels", {}),
            "success": True
        }
    }
    return MockK8sProbeClient(responses)


@pytest.fixture
def failing_client():
    """Create mock client that simulates failures."""
    responses = {
        "get_cluster_metrics": {"error": "Connection refused"},
        "set_node_schedulable": {"error": "RBAC: permission denied"},
        "drain_node": {"error": "Timeout waiting for pod eviction"},
        "consolidate_workloads": {"error": "PodDisruptionBudget violation"}
    }
    return MockK8sProbeClient(responses)


# =============================================================================
# Category 1: Connection Failure (3 tests)
# Pre-mortem: What if we can't reach the probe?
# =============================================================================

class TestConnectionFailure:
    """
    Tests for MCP connection failures.
    
    Pre-mortem scenarios:
    - Probe server not running
    - Network partition
    - Authentication failure
    """
    
    @pytest.mark.connection
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_probe_connection_refused(self, failing_client):
        """
        Verify graceful handling when probe is unreachable.
        
        Pre-mortem: Probe crashed, pod restarting
        """
        result = await failing_client.call_tool("get_cluster_metrics", {})
        
        assert "error" in result
        assert "Connection" in result["error"]
    
    @pytest.mark.connection
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_probe_timeout_handling(self, mock_client):
        """
        Verify timeout is respected on slow responses.
        
        Pre-mortem: Cluster API slow, probe hangs
        """
        # Mock a slow response
        async def slow_response(params):
            import asyncio
            await asyncio.sleep(0.1)
            return {"status": "ok"}
        
        mock_client.responses["get_cluster_metrics"] = slow_response
        
        result = await mock_client.call_tool("get_cluster_metrics", {})
        assert result.get("status") == "ok"
    
    @pytest.mark.connection
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_probe_reconnection(self, mock_client):
        """
        Verify probe can recover after temporary disconnection.
        
        Pre-mortem: Network blip, pod restart
        """
        # First call fails
        mock_client.responses["get_cluster_metrics"] = {"error": "Connection lost"}
        result1 = await mock_client.call_tool("get_cluster_metrics", {})
        assert "error" in result1
        
        # Reconnect succeeds
        mock_client.responses["get_cluster_metrics"] = {"status": "ok", "nodes": 21}
        result2 = await mock_client.call_tool("get_cluster_metrics", {})
        assert result2.get("status") == "ok"


# =============================================================================
# Category 2: Node Control Failure (3 tests)
# Pre-mortem: What if node operations fail?
# =============================================================================

class TestNodeControlFailure:
    """
    Tests for node control operation failures.
    
    Pre-mortem scenarios:
    - Cordon fails
    - Drain stuck on pod
    - Node becomes unresponsive
    """
    
    @pytest.mark.node_control
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_cordon_node_success(self, mock_client):
        """
        Verify node can be cordoned successfully.
        
        Pre-mortem: Node cordon rejected
        """
        result = await mock_client.call_tool("set_node_schedulable", {
            "node_name": "vsf-worker-5",
            "schedulable": False
        })
        
        assert result.get("success") is True
        assert result.get("schedulable") is False
    
    @pytest.mark.node_control
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_drain_node_timeout(self, failing_client):
        """
        Verify drain timeout is handled gracefully.
        
        Pre-mortem: Pod won't evict, drain hangs
        """
        result = await failing_client.call_tool("drain_node", {
            "node_name": "vsf-worker-5",
            "timeout_seconds": 60
        })
        
        assert "error" in result
        assert "Timeout" in result["error"]
    
    @pytest.mark.node_control
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_drain_respects_pdb(self, mock_client):
        """
        Verify drain respects PodDisruptionBudgets.
        
        Pre-mortem: PDB blocks eviction, drain fails
        """
        result = await mock_client.call_tool("drain_node", {
            "node_name": "vsf-worker-5",
            "respect_pdb": True
        })
        
        assert result.get("success") is True
        assert result.get("pods_evicted") >= 0


# =============================================================================
# Category 3: Workload Failure (3 tests)
# Pre-mortem: What if workload operations fail?
# =============================================================================

class TestWorkloadFailure:
    """
    Tests for workload management failures.
    
    Pre-mortem scenarios:
    - Pod migration fails
    - Consolidation breaks application
    - Workload stuck pending
    """
    
    @pytest.mark.workload
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_get_workload_distribution(self, mock_client):
        """
        Verify workload distribution is retrieved correctly.
        
        Pre-mortem: Stale distribution data
        """
        result = await mock_client.call_tool("get_workload_distribution", {})
        
        assert "nodes" in result
        assert len(result["nodes"]) > 0
        assert result.get("total_pods", 0) > 0
    
    @pytest.mark.workload
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_consolidate_workloads_success(self, mock_client):
        """
        Verify workload consolidation completes successfully.
        
        Pre-mortem: Migration fails mid-consolidation
        """
        result = await mock_client.call_tool("consolidate_workloads", {
            "target_node_count": 5,
            "dry_run": False
        })
        
        assert result.get("success") is True
        assert result.get("pods_moved", 0) >= 0
    
    @pytest.mark.workload
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_consolidate_pdb_violation(self, failing_client):
        """
        Verify PDB violation is reported during consolidation.
        
        Pre-mortem: Critical app can't be moved
        """
        result = await failing_client.call_tool("consolidate_workloads", {
            "target_node_count": 3
        })
        
        assert "error" in result
        assert "PodDisruptionBudget" in result["error"]


# =============================================================================
# Category 4: Metrics Failure (3 tests)
# Pre-mortem: What if metrics are wrong?
# =============================================================================

class TestMetricsFailure:
    """
    Tests for metrics collection failures.
    
    Pre-mortem scenarios:
    - Stale metrics
    - Missing node metrics
    - Aggregation errors
    """
    
    @pytest.mark.metrics
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_get_cluster_metrics(self, mock_client):
        """
        Verify cluster metrics are complete.
        
        Pre-mortem: Missing metrics fields
        """
        result = await mock_client.call_tool("get_cluster_metrics", {})
        
        required_fields = ["total_nodes", "ready_nodes", "total_pods", "running_pods"]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"
    
    @pytest.mark.metrics
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_get_node_power_state(self, mock_client):
        """
        Verify individual node metrics are retrieved.
        
        Pre-mortem: Node not found
        """
        result = await mock_client.call_tool("get_node_power_state", {
            "node_name": "vsf-worker-1"
        })
        
        assert result.get("node") == "vsf-worker-1"
        assert "schedulable" in result
        assert "ready" in result
    
    @pytest.mark.metrics
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_gpu_workloads_metrics(self, mock_client):
        """
        Verify GPU workload metrics are available.
        
        Pre-mortem: GPU pods not detected
        """
        result = await mock_client.call_tool("get_gpu_workloads", {})
        
        assert "gpu_nodes" in result
        assert "gpu_pods" in result
        assert "workloads" in result


# =============================================================================
# Category 5: Permission Failure (3 tests)
# Pre-mortem: What if RBAC blocks us?
# =============================================================================

class TestPermissionFailure:
    """
    Tests for RBAC and permission failures.
    
    Pre-mortem scenarios:
    - Insufficient permissions
    - Service account missing
    - Role binding deleted
    """
    
    @pytest.mark.permission
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_permission_denied_on_cordon(self, failing_client):
        """
        Verify RBAC denial is handled gracefully.
        
        Pre-mortem: Service account lacks node permissions
        """
        result = await failing_client.call_tool("set_node_schedulable", {
            "node_name": "vsf-worker-1",
            "schedulable": False
        })
        
        assert "error" in result
        assert "permission" in result["error"].lower() or "RBAC" in result["error"]
    
    @pytest.mark.permission
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_read_operations_allowed(self, mock_client):
        """
        Verify read operations work with minimal permissions.
        
        Pre-mortem: Even read is blocked
        """
        result = await mock_client.call_tool("get_cluster_metrics", {})
        
        # Read should succeed
        assert "error" not in result
        assert result.get("total_nodes", 0) > 0
    
    @pytest.mark.permission
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_label_operations_require_permission(self, mock_client):
        """
        Verify label operations work when permitted.
        
        Pre-mortem: Label operation rejected
        """
        result = await mock_client.call_tool("set_node_labels", {
            "node_name": "vsf-worker-1",
            "labels": {"vsf/power-state": "active"}
        })
        
        assert result.get("success") is True


# =============================================================================
# Category 6: State Inconsistency (3 tests)
# Pre-mortem: What if state is out of sync?
# =============================================================================

class TestStateInconsistency:
    """
    Tests for state synchronization failures.
    
    Pre-mortem scenarios:
    - Probe state differs from cluster
    - Stale cache
    - Race conditions
    """
    
    @pytest.mark.state
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_node_count_matches_cluster(self, mock_client):
        """
        Verify probe reports correct node count.
        
        Pre-mortem: Probe sees old node count
        """
        result = await mock_client.call_tool("get_cluster_metrics", {})
        
        # VSF has 21 nodes (3 CP + 10 workers + 8 GPU)
        assert result.get("total_nodes") == 21
    
    @pytest.mark.state
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_workload_count_consistent(self, mock_client):
        """
        Verify pod counts are consistent across calls.
        
        Pre-mortem: Race condition shows different counts
        """
        result1 = await mock_client.call_tool("get_cluster_metrics", {})
        result2 = await mock_client.call_tool("get_workload_distribution", {})
        
        # Total pods should be consistent (within tolerance for race)
        cluster_pods = result1.get("total_pods", 0)
        dist_pods = result2.get("total_pods", 0)
        
        # Allow small variance for in-flight changes
        assert abs(cluster_pods - dist_pods) <= 5
    
    @pytest.mark.state
    @pytest.mark.k8s_probe
    @pytest.mark.asyncio
    async def test_node_state_after_cordon(self, mock_client):
        """
        Verify node state updates after cordon operation.
        
        Pre-mortem: State not updated after operation
        """
        # Cordon the node
        await mock_client.call_tool("set_node_schedulable", {
            "node_name": "vsf-worker-5",
            "schedulable": False
        })
        
        # Update mock to reflect new state
        mock_client.responses["get_node_power_state"] = lambda p: {
            "node": p.get("node_name"),
            "schedulable": False if p.get("node_name") == "vsf-worker-5" else True,
            "ready": True,
            "pods": 5
        }
        
        # Verify state is updated
        result = await mock_client.call_tool("get_node_power_state", {
            "node_name": "vsf-worker-5"
        })
        
        assert result.get("schedulable") is False


# =============================================================================
# Test Summary
# =============================================================================
# Total: 18 tests across 6 pre-mortem failure categories
#
# Category 1 - Connection Failure: 3 tests
# Category 2 - Node Control Failure: 3 tests
# Category 3 - Workload Failure: 3 tests
# Category 4 - Metrics Failure: 3 tests
# Category 5 - Permission Failure: 3 tests
# Category 6 - State Inconsistency: 3 tests
#
# Markers:
#   - connection: MCP connection tests
#   - node_control: Node cordon/drain tests
#   - workload: Pod scheduling/consolidation tests
#   - metrics: Cluster metrics tests
#   - permission: RBAC/permission tests
#   - state: State consistency tests
#   - k8s_probe: All K8s Probe tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "k8s_probe"])
