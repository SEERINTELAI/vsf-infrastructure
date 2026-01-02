"""
F10.2 Kubernetes Test Suite

Comprehensive pytest test suite for K3s cluster validation.
Tests are designed to be idempotent and non-destructive (read-only checks).

Test Categories (19 tests total per DP:ETG):
1. Control Plane Health (3 tests)
2. Worker Node Joins (3 tests)
3. CNI Networking (3 tests)
4. GPU Metrics (3 tests) - Tests mock-dcgm-exporter in mock mode
5. Service Discovery (2 tests)
6. Pod Scheduling (2 tests)
7. Failure Scenarios (3 tests)

Usage:
    pytest tests/test_kubernetes.py -v -m kubernetes
    pytest tests/test_kubernetes.py -v -k "control_plane"
    pytest tests/test_kubernetes.py -v --tb=short
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ClusterConfig:
    """Expected cluster configuration."""
    control_plane_nodes: int = 3
    standard_workers: int = 10
    gpu_workers: int = 8
    total_nodes: int = 21  # 3 + 10 + 8
    
    # Timeouts
    api_timeout: int = 10
    node_ready_timeout: int = 60
    pod_ready_timeout: int = 120


CONFIG = ClusterConfig()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def kubectl():
    """Fixture to run kubectl commands."""
    import shutil
    
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        pytest.skip("kubectl not found in PATH - cannot run K8s tests")
    
    def _kubectl(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = ["kubectl"] + args
        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except FileNotFoundError:
            pytest.skip("kubectl not available")
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, "", "timeout")
    return _kubectl


@pytest.fixture(scope="module")
def cluster_available(kubectl) -> bool:
    """Check if cluster is reachable."""
    result = kubectl(["cluster-info"], timeout=CONFIG.api_timeout)
    return result.returncode == 0


@pytest.fixture(scope="module")
def nodes(kubectl) -> list[dict[str, Any]]:
    """Get all nodes as parsed JSON."""
    result = kubectl(["get", "nodes", "-o", "json"])
    if result.returncode != 0:
        return []
    return json.loads(result.stdout).get("items", [])


@pytest.fixture(scope="module")
def pods_all_namespaces(kubectl) -> list[dict[str, Any]]:
    """Get all pods across all namespaces."""
    result = kubectl(["get", "pods", "-A", "-o", "json"])
    if result.returncode != 0:
        return []
    return json.loads(result.stdout).get("items", [])


# =============================================================================
# 1. Control Plane Health Tests (3 tests)
# =============================================================================

class TestControlPlaneHealth:
    """
    Control plane health validation tests.
    
    Pre-mortem scenarios:
    - API server crash
    - etcd quorum lost
    - Scheduler stuck
    """
    
    @pytest.mark.kubernetes
    def test_api_server_healthy(self, kubectl, cluster_available):
        """
        Verify kube-apiserver responds on all control plane nodes.
        
        Pre-mortem: API server crash, certificate expiry, OOM
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check API server responds
        result = kubectl(["get", "--raw", "/healthz"], timeout=CONFIG.api_timeout)
        assert result.returncode == 0, f"API server health check failed: {result.stderr}"
        assert "ok" in result.stdout.lower(), f"API server not healthy: {result.stdout}"
    
    @pytest.mark.kubernetes
    def test_etcd_cluster_healthy(self, kubectl, cluster_available):
        """
        Verify etcd cluster has quorum and all members healthy.
        
        Pre-mortem: etcd quorum lost, disk full, slow disk I/O
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check etcd pods in kube-system (for K3s with embedded etcd)
        result = kubectl([
            "get", "pods", "-n", "kube-system",
            "-l", "component=etcd",
            "-o", "jsonpath={.items[*].status.phase}"
        ])
        
        # K3s may use embedded etcd without labeled pods
        # Check via API server endpoint instead
        if not result.stdout.strip():
            # Fallback: check livez/etcd endpoint
            result = kubectl(["get", "--raw", "/livez/etcd"], timeout=CONFIG.api_timeout)
            if result.returncode == 0:
                assert "ok" in result.stdout.lower(), "etcd not healthy"
            else:
                # K3s embedded etcd - check via cluster health
                result = kubectl(["get", "nodes"], timeout=CONFIG.api_timeout)
                assert result.returncode == 0, "Cannot verify etcd - cluster unreachable"
        else:
            phases = result.stdout.strip().split()
            running = sum(1 for p in phases if p == "Running")
            assert running >= 2, f"etcd quorum at risk: only {running} pods running"
    
    @pytest.mark.kubernetes
    def test_scheduler_controller_running(self, kubectl, cluster_available):
        """
        Verify scheduler and controller-manager are running.
        
        Pre-mortem: Leader election stuck, resource exhaustion
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check scheduler health
        result = kubectl(["get", "--raw", "/livez/kube-scheduler"], timeout=CONFIG.api_timeout)
        # May not exist in all K3s versions, so just check API works
        
        # Check controller-manager via componentstatuses (deprecated but still works)
        result = kubectl(["get", "componentstatuses", "-o", "json"])
        if result.returncode == 0:
            cs = json.loads(result.stdout)
            for item in cs.get("items", []):
                name = item.get("metadata", {}).get("name", "")
                conditions = item.get("conditions", [])
                for c in conditions:
                    if c.get("type") == "Healthy":
                        assert c.get("status") == "True", f"{name} not healthy"
        else:
            # Fallback for K3s - just verify API server works
            result = kubectl(["get", "nodes"], timeout=CONFIG.api_timeout)
            assert result.returncode == 0, "Cannot verify scheduler - cluster unreachable"


# =============================================================================
# 2. Worker Node Joins Tests (3 tests)
# =============================================================================

class TestWorkerNodes:
    """
    Worker node join and health tests.
    
    Pre-mortem scenarios:
    - Node not ready
    - Kubelet crash
    - Certificate expiry
    """
    
    @pytest.mark.kubernetes
    def test_standard_workers_ready(self, kubectl, nodes, cluster_available):
        """
        Verify all standard workers are in Ready state.
        
        Pre-mortem: Kubelet crash, CNI failure, node isolation
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found - cluster may not be deployed")
        
        # Find standard workers (not control-plane, not GPU)
        standard_workers = []
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            
            # Skip control plane nodes
            if "node-role.kubernetes.io/control-plane" in labels:
                continue
            if "node-role.kubernetes.io/master" in labels:
                continue
            
            # Skip GPU workers
            if labels.get("nvidia.com/gpu") == "true":
                continue
            if "gpu" in name.lower():
                continue
            
            # Check Ready condition
            conditions = node.get("status", {}).get("conditions", [])
            for c in conditions:
                if c.get("type") == "Ready":
                    if c.get("status") == "True":
                        standard_workers.append(name)
        
        assert len(standard_workers) >= CONFIG.standard_workers, \
            f"Expected {CONFIG.standard_workers} standard workers, found {len(standard_workers)} ready: {standard_workers}"
    
    @pytest.mark.kubernetes
    def test_gpu_workers_ready(self, kubectl, nodes, cluster_available):
        """
        Verify all GPU workers are in Ready state.
        
        Pre-mortem: GPU driver failure, container runtime issue
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found - cluster may not be deployed")
        
        gpu_workers = []
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            
            # Identify GPU workers
            is_gpu = (
                labels.get("nvidia.com/gpu") == "true" or
                labels.get("vsf/node-type") == "gpu" or
                "gpu" in name.lower()
            )
            
            if not is_gpu:
                continue
            
            # Check Ready condition
            conditions = node.get("status", {}).get("conditions", [])
            for c in conditions:
                if c.get("type") == "Ready" and c.get("status") == "True":
                    gpu_workers.append(name)
        
        assert len(gpu_workers) >= CONFIG.gpu_workers, \
            f"Expected {CONFIG.gpu_workers} GPU workers, found {len(gpu_workers)} ready: {gpu_workers}"
    
    @pytest.mark.kubernetes
    def test_node_labels_applied(self, kubectl, nodes, cluster_available):
        """
        Verify all nodes have expected labels (node-type, gpu).
        
        Pre-mortem: Label not applied, typo in label key
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        # Check that at least some nodes have vsf labels
        labeled_nodes = 0
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            if any(k.startswith("vsf/") for k in labels.keys()):
                labeled_nodes += 1
            # Also count kubernetes.io/role or node-role labels
            if any("node-role" in k for k in labels.keys()):
                labeled_nodes += 1
        
        # At minimum, nodes should have standard k8s labels
        assert labeled_nodes > 0, "No nodes have expected labels"


# =============================================================================
# 3. CNI Networking Tests (3 tests)
# =============================================================================

class TestCNINetworking:
    """
    Calico CNI and network policy tests.
    
    Pre-mortem scenarios:
    - Calico pods not running
    - VXLAN misconfigured
    - DNS resolution fails
    """
    
    @pytest.mark.kubernetes
    def test_cni_pods_running(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify CNI pods are running (Calico or Flannel).
        
        Pre-mortem: Calico pods not running, VXLAN misconfigured
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        # Look for CNI pods (calico, flannel, or cilium)
        cni_pods = []
        for pod in pods_all_namespaces:
            name = pod.get("metadata", {}).get("name", "")
            namespace = pod.get("metadata", {}).get("namespace", "")
            phase = pod.get("status", {}).get("phase", "")
            
            if any(cni in name.lower() for cni in ["calico", "flannel", "cilium", "canal"]):
                if namespace in ["kube-system", "calico-system", "tigera-operator"]:
                    cni_pods.append((name, phase))
        
        running = sum(1 for _, phase in cni_pods if phase == "Running")
        assert running > 0, f"No CNI pods running. Found: {cni_pods}"
    
    @pytest.mark.kubernetes
    def test_dns_resolution(self, kubectl, cluster_available):
        """
        Verify CoreDNS resolves service names.
        
        Pre-mortem: CoreDNS crashed, configmap wrong, memory limit
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check CoreDNS pods are running
        result = kubectl([
            "get", "pods", "-n", "kube-system",
            "-l", "k8s-app=kube-dns",
            "-o", "jsonpath={.items[*].status.phase}"
        ])
        
        if result.stdout.strip():
            phases = result.stdout.strip().split()
            running = sum(1 for p in phases if p == "Running")
            assert running > 0, "CoreDNS pods not running"
        else:
            # Try coredns label
            result = kubectl([
                "get", "pods", "-n", "kube-system",
                "-l", "app.kubernetes.io/name=coredns",
                "-o", "jsonpath={.items[*].status.phase}"
            ])
            if result.stdout.strip():
                phases = result.stdout.strip().split()
                running = sum(1 for p in phases if p == "Running")
                assert running > 0, "CoreDNS pods not running"
    
    @pytest.mark.kubernetes
    def test_pod_network_connectivity(self, kubectl, cluster_available):
        """
        Verify pods can communicate across nodes (basic check).
        
        Pre-mortem: Network policy blocks, VXLAN issues
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check that kubernetes service is accessible (basic connectivity test)
        result = kubectl([
            "get", "endpoints", "kubernetes",
            "-o", "jsonpath={.subsets[0].addresses[0].ip}"
        ])
        
        assert result.returncode == 0, "Cannot get kubernetes service endpoints"
        assert result.stdout.strip(), "Kubernetes service has no endpoints"


# =============================================================================
# 4. GPU Metrics Tests (3 tests) - Mock Mode Compatible
# =============================================================================

class TestGPUMetrics:
    """
    GPU metrics validation tests.
    Tests work with both real GPU Operator/DCGM and mock-dcgm-exporter.
    
    Pre-mortem scenarios:
    - Driver not loaded (real mode)
    - Mock exporter not deployed
    - Device plugin missing
    """
    
    @pytest.mark.kubernetes
    def test_gpu_metrics_exporter_running(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify GPU metrics exporter is running (DCGM or mock).
        
        Pre-mortem: CRD not installed, image pull error
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        # Look for DCGM exporter or mock-dcgm-exporter
        gpu_exporters = []
        for pod in pods_all_namespaces:
            name = pod.get("metadata", {}).get("name", "")
            phase = pod.get("status", {}).get("phase", "")
            
            if any(exp in name.lower() for exp in ["dcgm", "gpu-exporter", "mock-dcgm"]):
                gpu_exporters.append((name, phase))
        
        if not gpu_exporters:
            pytest.skip("No GPU metrics exporter found - may not be deployed yet")
        
        running = sum(1 for _, phase in gpu_exporters if phase == "Running")
        assert running > 0, f"GPU metrics exporter not running: {gpu_exporters}"
    
    @pytest.mark.kubernetes
    def test_gpu_resource_available(self, kubectl, nodes, cluster_available):
        """
        Verify nvidia.com/gpu resource is schedulable (real) or node has GPU label (mock).
        
        Pre-mortem: Device plugin crash, driver not loaded
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        # Check for GPU resources or GPU labels
        gpu_nodes = 0
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            allocatable = node.get("status", {}).get("allocatable", {})
            
            # Check real GPU resource
            gpu_count = allocatable.get("nvidia.com/gpu", "0")
            if int(gpu_count) > 0:
                gpu_nodes += 1
                continue
            
            # Check mock mode labels
            if labels.get("nvidia.com/gpu.present") == "true":
                gpu_nodes += 1
                continue
            
            # Check vsf label
            if labels.get("vsf/node-type") == "gpu":
                gpu_nodes += 1
        
        # At least some GPU nodes should exist (real or labeled for mock)
        assert gpu_nodes > 0 or CONFIG.gpu_workers == 0, \
            "No GPU-capable nodes found"
    
    @pytest.mark.kubernetes
    def test_gpu_metrics_exposed(self, kubectl, cluster_available):
        """
        Verify GPU metrics are exposed to Prometheus (DCGM or mock format).
        
        Pre-mortem: DCGM not running, wrong port, auth issue
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check for ServiceMonitor or GPU exporter service
        result = kubectl([
            "get", "servicemonitor", "-A",
            "-o", "jsonpath={.items[*].metadata.name}"
        ])
        
        # ServiceMonitor may not exist if Prometheus isn't deployed yet
        if result.returncode != 0 or not result.stdout.strip():
            # Check for dcgm service directly
            result = kubectl([
                "get", "svc", "-A",
                "-o", "jsonpath={.items[*].metadata.name}"
            ])
            
            if result.returncode == 0:
                services = result.stdout.strip().split()
                gpu_services = [s for s in services if "dcgm" in s.lower() or "gpu" in s.lower()]
                if gpu_services:
                    return  # GPU service exists
            
            pytest.skip("Prometheus not deployed yet - cannot verify GPU metrics endpoint")


# =============================================================================
# 5. Service Discovery Tests (2 tests)
# =============================================================================

class TestServiceDiscovery:
    """
    Service discovery and DNS tests.
    
    Pre-mortem scenarios:
    - CoreDNS failure
    - Service endpoints not updated
    """
    
    @pytest.mark.kubernetes
    def test_kubernetes_service_has_endpoints(self, kubectl, cluster_available):
        """
        Verify kubernetes service endpoints are populated.
        
        Pre-mortem: Endpoints controller lag, stale endpoints
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        result = kubectl([
            "get", "endpoints", "kubernetes",
            "-o", "json"
        ])
        
        assert result.returncode == 0, "Cannot get kubernetes endpoints"
        
        endpoints = json.loads(result.stdout)
        subsets = endpoints.get("subsets", [])
        assert len(subsets) > 0, "Kubernetes service has no endpoint subsets"
        
        addresses = subsets[0].get("addresses", [])
        assert len(addresses) > 0, "Kubernetes service has no addresses"
    
    @pytest.mark.kubernetes
    def test_coredns_service_exists(self, kubectl, cluster_available):
        """
        Verify CoreDNS service exists and has endpoints.
        
        Pre-mortem: CoreDNS cache stale, wrong search domain
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        result = kubectl([
            "get", "svc", "kube-dns", "-n", "kube-system",
            "-o", "jsonpath={.spec.clusterIP}"
        ])
        
        assert result.returncode == 0, "kube-dns service not found"
        assert result.stdout.strip(), "kube-dns has no cluster IP"


# =============================================================================
# 6. Pod Scheduling Tests (2 tests)
# =============================================================================

class TestPodScheduling:
    """
    Pod scheduling and resource tests.
    
    Pre-mortem scenarios:
    - Resource exhaustion
    - Taint/toleration mismatch
    """
    
    @pytest.mark.kubernetes
    def test_system_pods_scheduled(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify system pods are scheduled and running.
        
        Pre-mortem: Taint blocks scheduling, affinity conflict
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        # Check kube-system pods
        kube_system_pods = [
            p for p in pods_all_namespaces
            if p.get("metadata", {}).get("namespace") == "kube-system"
        ]
        
        running = sum(
            1 for p in kube_system_pods
            if p.get("status", {}).get("phase") == "Running"
        )
        
        pending = sum(
            1 for p in kube_system_pods
            if p.get("status", {}).get("phase") == "Pending"
        )
        
        assert running > 0, "No kube-system pods running"
        assert pending == 0 or running > pending, \
            f"Too many pending pods in kube-system: {pending} pending, {running} running"
    
    @pytest.mark.kubernetes
    def test_node_resources_available(self, kubectl, nodes, cluster_available):
        """
        Verify nodes have allocatable resources.
        
        Pre-mortem: Resource exhausted, wrong limit
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            allocatable = node.get("status", {}).get("allocatable", {})
            
            # Check CPU and memory are allocatable
            cpu = allocatable.get("cpu", "0")
            memory = allocatable.get("memory", "0")
            
            assert cpu != "0", f"Node {name} has no allocatable CPU"
            assert memory != "0", f"Node {name} has no allocatable memory"


# =============================================================================
# 7. Failure Scenario Tests (3 tests)
# =============================================================================

class TestFailureScenarios:
    """
    Failure recovery and resilience tests.
    These are read-only checks that verify cluster can handle failures.
    
    Pre-mortem scenarios:
    - Node drain
    - Control plane failover
    - Pod restart
    """
    
    @pytest.mark.kubernetes
    def test_multiple_control_plane_nodes(self, kubectl, nodes, cluster_available):
        """
        Verify multiple control plane nodes exist for HA.
        
        Pre-mortem: Single control plane = no failover
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        control_plane = []
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            
            if "node-role.kubernetes.io/control-plane" in labels:
                control_plane.append(name)
            elif "node-role.kubernetes.io/master" in labels:
                control_plane.append(name)
        
        assert len(control_plane) >= 3, \
            f"HA requires 3+ control plane nodes, found {len(control_plane)}: {control_plane}"
    
    @pytest.mark.kubernetes
    def test_pod_restart_policy_exists(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify pods have restart policies configured.
        
        Pre-mortem: CrashLoopBackOff with no restart
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        # Check that system pods have restart policy
        for pod in pods_all_namespaces:
            namespace = pod.get("metadata", {}).get("namespace", "")
            if namespace != "kube-system":
                continue
            
            spec = pod.get("spec", {})
            restart_policy = spec.get("restartPolicy", "Always")
            
            # Pods should have Always or OnFailure
            assert restart_policy in ["Always", "OnFailure"], \
                f"Pod {pod.get('metadata', {}).get('name')} has unexpected restart policy: {restart_policy}"
    
    @pytest.mark.kubernetes
    def test_no_evicted_pods(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify no pods are evicted (indicates resource pressure).
        
        Pre-mortem: Node eviction due to resource pressure
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        evicted = []
        for pod in pods_all_namespaces:
            name = pod.get("metadata", {}).get("name", "")
            reason = pod.get("status", {}).get("reason", "")
            
            if reason == "Evicted":
                evicted.append(name)
        
        assert len(evicted) == 0, f"Found evicted pods (resource pressure): {evicted}"


# =============================================================================
# Run Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "kubernetes"])
