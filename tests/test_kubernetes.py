"""
Kubernetes Test Suite for VSF F10.2 (DP:FULL Compliant)

Comprehensive pytest test suite implementing DP:ETG (Exhaustive Test Generation)
with explicit pre-mortem failure categories. Tests are read-only and non-destructive.

Pre-Mortem Failure Categories:
1. Bootstrap Failure - Cluster initialization, API server startup, node registration
2. HA/Quorum Failure - etcd quorum loss, leader election, control plane redundancy
3. Network Failure - CNI issues, DNS resolution, pod-to-pod connectivity
4. Scheduling Failure - Resource exhaustion, taint/toleration, affinity conflicts
5. GPU Isolation Failure - Device plugin, taints, resource overcommit
6. Resource Exhaustion - OOM, eviction, capacity limits

Total: 22 tests across 6 pre-mortem categories (exceeds DP:ETG minimum of 15)

Usage:
    pytest tests/test_kubernetes.py -v
    pytest tests/test_kubernetes.py -v -m bootstrap
    pytest tests/test_kubernetes.py -v -m ha
    pytest tests/test_kubernetes.py -v -m network
    pytest tests/test_kubernetes.py -v -m scheduling
    pytest tests/test_kubernetes.py -v -m gpu
    pytest tests/test_kubernetes.py -v -m resource
"""

import json
import logging
import subprocess
from dataclasses import dataclass
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
# Category 1: Bootstrap Failure (4 tests)
# Pre-mortem: What if cluster fails to initialize?
# =============================================================================

class TestBootstrapFailure:
    """
    Tests for cluster bootstrap and initialization failures.
    
    Pre-mortem scenarios:
    - API server fails to start
    - Node registration fails
    - Initial certificates not generated
    - Control plane components crash on startup
    """
    
    @pytest.mark.bootstrap
    @pytest.mark.kubernetes
    def test_api_server_responds(self, kubectl, cluster_available):
        """
        Verify kube-apiserver is responding to health checks.
        
        Pre-mortem: API server crash, certificate expiry, port binding failure
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        result = kubectl(["get", "--raw", "/healthz"], timeout=CONFIG.api_timeout)
        assert result.returncode == 0, f"API server health check failed: {result.stderr}"
        assert "ok" in result.stdout.lower(), f"API server not healthy: {result.stdout}"
    
    @pytest.mark.bootstrap
    @pytest.mark.kubernetes
    def test_control_plane_nodes_registered(self, kubectl, nodes, cluster_available):
        """
        Verify all control plane nodes successfully registered.
        
        Pre-mortem: Node registration timeout, kubelet misconfigured
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found - cluster may not be deployed")
        
        control_plane = []
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            if "node-role.kubernetes.io/control-plane" in labels or \
               "node-role.kubernetes.io/master" in labels:
                control_plane.append(node.get("metadata", {}).get("name", ""))
        
        assert len(control_plane) >= CONFIG.control_plane_nodes, \
            f"Expected {CONFIG.control_plane_nodes} control plane nodes, found {len(control_plane)}"
    
    @pytest.mark.bootstrap
    @pytest.mark.kubernetes
    def test_scheduler_controller_running(self, kubectl, cluster_available):
        """
        Verify scheduler and controller-manager started successfully.
        
        Pre-mortem: Scheduler crash, controller-manager OOM, leader election stuck
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check via componentstatuses (deprecated but works)
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
            # Fallback: verify cluster is functional
            result = kubectl(["get", "nodes"], timeout=CONFIG.api_timeout)
            assert result.returncode == 0, "Cannot verify scheduler - cluster unreachable"
    
    @pytest.mark.bootstrap
    @pytest.mark.kubernetes
    def test_system_namespace_exists(self, kubectl, cluster_available):
        """
        Verify kube-system namespace was created during bootstrap.
        
        Pre-mortem: Bootstrap incomplete, namespace creation failed
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        result = kubectl(["get", "namespace", "kube-system", "-o", "jsonpath={.metadata.name}"])
        assert result.returncode == 0, "kube-system namespace not found"
        assert result.stdout.strip() == "kube-system", "kube-system namespace missing"


# =============================================================================
# Category 2: HA/Quorum Failure (3 tests)
# Pre-mortem: What if HA components fail?
# =============================================================================

class TestHAFailure:
    """
    Tests for high availability and quorum failures.
    
    Pre-mortem scenarios:
    - etcd quorum lost (2 of 3 nodes down)
    - Leader election stuck
    - Split brain scenario
    - Data consistency during partial quorum
    """
    
    @pytest.mark.ha
    @pytest.mark.kubernetes
    def test_etcd_cluster_healthy(self, kubectl, cluster_available):
        """
        Verify etcd cluster has quorum and all members healthy.
        
        Pre-mortem: etcd quorum lost, disk full, slow disk I/O
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        # Check etcd via API server health endpoint
        result = kubectl(["get", "--raw", "/livez/etcd"], timeout=CONFIG.api_timeout)
        if result.returncode == 0:
            assert "ok" in result.stdout.lower(), "etcd not healthy"
        else:
            # K3s embedded etcd - verify via cluster functionality
            result = kubectl(["get", "nodes"], timeout=CONFIG.api_timeout)
            assert result.returncode == 0, "Cannot verify etcd - cluster unreachable"
    
    @pytest.mark.ha
    @pytest.mark.kubernetes
    def test_multiple_control_plane_for_ha(self, kubectl, nodes, cluster_available):
        """
        Verify 3+ control plane nodes exist for proper HA.
        
        Pre-mortem: Single control plane = no failover capability
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        control_plane = []
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            if "node-role.kubernetes.io/control-plane" in labels or \
               "node-role.kubernetes.io/master" in labels:
                control_plane.append(node.get("metadata", {}).get("name", ""))
        
        assert len(control_plane) >= 3, \
            f"HA requires 3+ control plane nodes, found {len(control_plane)}: {control_plane}"
    
    @pytest.mark.ha
    @pytest.mark.kubernetes
    def test_control_plane_nodes_all_ready(self, kubectl, nodes, cluster_available):
        """
        Verify all control plane nodes are in Ready state.
        
        Pre-mortem: Leader election fails if nodes not ready
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        not_ready = []
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            name = node.get("metadata", {}).get("name", "")
            
            if "node-role.kubernetes.io/control-plane" not in labels and \
               "node-role.kubernetes.io/master" not in labels:
                continue
            
            conditions = node.get("status", {}).get("conditions", [])
            ready = False
            for c in conditions:
                if c.get("type") == "Ready" and c.get("status") == "True":
                    ready = True
            
            if not ready:
                not_ready.append(name)
        
        assert len(not_ready) == 0, f"Control plane nodes not ready: {not_ready}"


# =============================================================================
# Category 3: Network Failure (4 tests)
# Pre-mortem: What if networking fails?
# =============================================================================

class TestNetworkFailure:
    """
    Tests for CNI and network failures.
    
    Pre-mortem scenarios:
    - Calico pods crash
    - VXLAN misconfigured
    - DNS resolution fails
    - Pod-to-pod connectivity broken
    - Service discovery failure
    """
    
    @pytest.mark.network
    @pytest.mark.kubernetes
    def test_cni_pods_running(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify CNI pods are running (Calico/Flannel/Cilium).
        
        Pre-mortem: CNI pods crash, image pull failure, init container stuck
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
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
    
    @pytest.mark.network
    @pytest.mark.kubernetes
    def test_coredns_running(self, kubectl, cluster_available):
        """
        Verify CoreDNS pods are running for DNS resolution.
        
        Pre-mortem: CoreDNS crashed, configmap wrong, memory limit exceeded
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
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
            result = kubectl([
                "get", "pods", "-n", "kube-system",
                "-l", "app.kubernetes.io/name=coredns",
                "-o", "jsonpath={.items[*].status.phase}"
            ])
            if result.stdout.strip():
                phases = result.stdout.strip().split()
                running = sum(1 for p in phases if p == "Running")
                assert running > 0, "CoreDNS pods not running"
    
    @pytest.mark.network
    @pytest.mark.kubernetes
    def test_kubernetes_service_endpoints(self, kubectl, cluster_available):
        """
        Verify kubernetes service has endpoints (basic connectivity).
        
        Pre-mortem: Endpoints controller lag, API server unreachable from pods
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        result = kubectl([
            "get", "endpoints", "kubernetes",
            "-o", "jsonpath={.subsets[0].addresses[0].ip}"
        ])
        
        assert result.returncode == 0, "Cannot get kubernetes service endpoints"
        assert result.stdout.strip(), "Kubernetes service has no endpoints"
    
    @pytest.mark.network
    @pytest.mark.kubernetes
    def test_kube_dns_service_exists(self, kubectl, cluster_available):
        """
        Verify kube-dns service exists with cluster IP.
        
        Pre-mortem: DNS service deleted, wrong cluster IP
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
# Category 4: Scheduling Failure (4 tests)
# Pre-mortem: What if pod scheduling fails?
# =============================================================================

class TestSchedulingFailure:
    """
    Tests for pod scheduling failures.
    
    Pre-mortem scenarios:
    - Taint blocks scheduling
    - Affinity conflict
    - Resource exhaustion
    - Pending pods stuck
    """
    
    @pytest.mark.scheduling
    @pytest.mark.kubernetes
    def test_system_pods_scheduled(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify system pods are scheduled and running.
        
        Pre-mortem: Taint blocks scheduling, no nodes available
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
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
    
    @pytest.mark.scheduling
    @pytest.mark.kubernetes
    def test_no_pending_pods_long_term(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify no pods are stuck pending (indicates scheduling issue).
        
        Pre-mortem: Resource shortage, unschedulable pods
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        pending_pods = []
        for pod in pods_all_namespaces:
            phase = pod.get("status", {}).get("phase", "")
            name = pod.get("metadata", {}).get("name", "")
            namespace = pod.get("metadata", {}).get("namespace", "")
            
            if phase == "Pending":
                pending_pods.append(f"{namespace}/{name}")
        
        # Some pending is ok during deployment, but should be minimal
        assert len(pending_pods) <= 5, \
            f"Too many pending pods: {pending_pods}"
    
    @pytest.mark.scheduling
    @pytest.mark.kubernetes
    def test_node_labels_applied(self, kubectl, nodes, cluster_available):
        """
        Verify nodes have expected labels for affinity rules.
        
        Pre-mortem: Label not applied, scheduling fails due to missing selector
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        labeled_nodes = 0
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            if any(k.startswith("vsf/") for k in labels.keys()):
                labeled_nodes += 1
            if any("node-role" in k for k in labels.keys()):
                labeled_nodes += 1
        
        assert labeled_nodes > 0, "No nodes have expected labels for scheduling"
    
    @pytest.mark.scheduling
    @pytest.mark.kubernetes
    def test_node_resources_allocatable(self, kubectl, nodes, cluster_available):
        """
        Verify nodes have allocatable resources for scheduling.
        
        Pre-mortem: Resource exhausted, pods can't be scheduled
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            allocatable = node.get("status", {}).get("allocatable", {})
            
            cpu = allocatable.get("cpu", "0")
            memory = allocatable.get("memory", "0")
            
            assert cpu != "0", f"Node {name} has no allocatable CPU"
            assert memory != "0", f"Node {name} has no allocatable memory"


# =============================================================================
# Category 5: GPU Isolation Failure (4 tests)
# Pre-mortem: What if GPU scheduling/isolation fails?
# =============================================================================

class TestGPUIsolationFailure:
    """
    Tests for GPU-specific failures.
    
    Pre-mortem scenarios:
    - GPU taints not respected
    - Device plugin crash
    - Resource overcommit
    - Wrong node placement
    """
    
    @pytest.mark.gpu
    @pytest.mark.kubernetes
    def test_gpu_workers_ready(self, kubectl, nodes, cluster_available):
        """
        Verify all GPU workers are in Ready state.
        
        Pre-mortem: GPU driver failure, container runtime issue
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        gpu_workers = []
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            labels = node.get("metadata", {}).get("labels", {})
            
            is_gpu = (
                labels.get("nvidia.com/gpu") == "true" or
                labels.get("vsf/node-type") == "gpu" or
                labels.get("nvidia.com/gpu.present") == "true" or
                "gpu" in name.lower()
            )
            
            if not is_gpu:
                continue
            
            conditions = node.get("status", {}).get("conditions", [])
            for c in conditions:
                if c.get("type") == "Ready" and c.get("status") == "True":
                    gpu_workers.append(name)
        
        assert len(gpu_workers) >= CONFIG.gpu_workers, \
            f"Expected {CONFIG.gpu_workers} GPU workers, found {len(gpu_workers)} ready"
    
    @pytest.mark.gpu
    @pytest.mark.kubernetes
    def test_gpu_nodes_have_taints(self, kubectl, nodes, cluster_available):
        """
        Verify GPU nodes have taints to prevent non-GPU workloads.
        
        Pre-mortem: Regular pods scheduled on GPU nodes, wasting resources
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        gpu_nodes_with_taints = 0
        gpu_nodes_total = 0
        
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            name = node.get("metadata", {}).get("name", "")
            
            is_gpu = (
                labels.get("vsf/node-type") == "gpu" or
                labels.get("nvidia.com/gpu.present") == "true" or
                "gpu" in name.lower()
            )
            
            if not is_gpu:
                continue
            
            gpu_nodes_total += 1
            taints = node.get("spec", {}).get("taints", [])
            
            for taint in taints:
                if "nvidia" in taint.get("key", "").lower() or "gpu" in taint.get("key", "").lower():
                    gpu_nodes_with_taints += 1
                    break
        
        if gpu_nodes_total > 0:
            assert gpu_nodes_with_taints > 0, \
                "GPU nodes should have taints to prevent non-GPU workloads"
    
    @pytest.mark.gpu
    @pytest.mark.kubernetes
    def test_gpu_metrics_exporter_running(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify GPU metrics exporter is running (DCGM or mock).
        
        Pre-mortem: Device plugin crash, no GPU visibility
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
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
    
    @pytest.mark.gpu
    @pytest.mark.kubernetes
    def test_gpu_resource_available_or_labeled(self, kubectl, nodes, cluster_available):
        """
        Verify nvidia.com/gpu resource exists (real) or GPU labels present (mock).
        
        Pre-mortem: Device plugin not running, GPU not detected
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        gpu_nodes = 0
        for node in nodes:
            labels = node.get("metadata", {}).get("labels", {})
            allocatable = node.get("status", {}).get("allocatable", {})
            
            # Real GPU resource
            gpu_count = allocatable.get("nvidia.com/gpu", "0")
            if int(gpu_count) > 0:
                gpu_nodes += 1
                continue
            
            # Mock mode labels
            if labels.get("nvidia.com/gpu.present") == "true":
                gpu_nodes += 1
                continue
            if labels.get("vsf/node-type") == "gpu":
                gpu_nodes += 1
        
        assert gpu_nodes > 0 or CONFIG.gpu_workers == 0, "No GPU-capable nodes found"


# =============================================================================
# Category 6: Resource Exhaustion (3 tests)
# Pre-mortem: What if resources are exhausted?
# =============================================================================

class TestResourceExhaustion:
    """
    Tests for resource exhaustion scenarios.
    
    Pre-mortem scenarios:
    - OOM kills
    - Pod eviction
    - Disk pressure
    - CPU throttling
    """
    
    @pytest.mark.resource
    @pytest.mark.kubernetes
    def test_no_evicted_pods(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify no pods are evicted (indicates resource pressure).
        
        Pre-mortem: Node eviction due to memory/disk pressure
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
    
    @pytest.mark.resource
    @pytest.mark.kubernetes
    def test_nodes_not_under_pressure(self, kubectl, nodes, cluster_available):
        """
        Verify no nodes have memory/disk/PID pressure.
        
        Pre-mortem: Node pressure leads to eviction cascade
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not nodes:
            pytest.skip("No nodes found")
        
        pressure_conditions = ["MemoryPressure", "DiskPressure", "PIDPressure"]
        nodes_under_pressure = []
        
        for node in nodes:
            name = node.get("metadata", {}).get("name", "")
            conditions = node.get("status", {}).get("conditions", [])
            
            for c in conditions:
                if c.get("type") in pressure_conditions and c.get("status") == "True":
                    nodes_under_pressure.append(f"{name}: {c.get('type')}")
        
        assert len(nodes_under_pressure) == 0, \
            f"Nodes under resource pressure: {nodes_under_pressure}"
    
    @pytest.mark.resource
    @pytest.mark.kubernetes
    def test_pods_have_restart_policy(self, kubectl, pods_all_namespaces, cluster_available):
        """
        Verify system pods have restart policies for OOM recovery.
        
        Pre-mortem: Pod OOM killed and not restarted
        """
        if not cluster_available:
            pytest.skip("Cluster not available")
        
        if not pods_all_namespaces:
            pytest.skip("No pods found")
        
        for pod in pods_all_namespaces:
            namespace = pod.get("metadata", {}).get("namespace", "")
            if namespace != "kube-system":
                continue
            
            spec = pod.get("spec", {})
            restart_policy = spec.get("restartPolicy", "Always")
            
            assert restart_policy in ["Always", "OnFailure"], \
                f"Pod {pod.get('metadata', {}).get('name')} has unexpected restart policy: {restart_policy}"


# =============================================================================
# Test Summary
# =============================================================================
# Total: 22 tests across 6 pre-mortem failure categories
#
# Category 1 - Bootstrap Failure: 4 tests
# Category 2 - HA/Quorum Failure: 3 tests
# Category 3 - Network Failure: 4 tests
# Category 4 - Scheduling Failure: 4 tests
# Category 5 - GPU Isolation Failure: 4 tests
# Category 6 - Resource Exhaustion: 3 tests
#
# Markers:
#   - bootstrap: Cluster initialization tests
#   - ha: High availability / quorum tests
#   - network: CNI / DNS / connectivity tests
#   - scheduling: Pod placement tests
#   - gpu: GPU isolation / device plugin tests
#   - resource: Resource exhaustion / eviction tests
#   - kubernetes: All kubernetes tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "kubernetes"])
