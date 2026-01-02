"""Pytest fixtures for VSF infrastructure testing."""
import logging
import subprocess
from pathlib import Path
from typing import Any
import pytest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Pytest Marker Registration
# =============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    # General categories
    config.addinivalue_line("markers", "infrastructure: Infrastructure validation tests")
    config.addinivalue_line("markers", "kubernetes: Kubernetes cluster tests")
    config.addinivalue_line("markers", "monitoring: Monitoring stack tests")
    config.addinivalue_line("markers", "integration: Integration tests (may modify state)")
    
    # Kubernetes pre-mortem categories (DP:ETG)
    config.addinivalue_line("markers", "bootstrap: Cluster initialization/bootstrap failure tests")
    config.addinivalue_line("markers", "ha: High availability / quorum failure tests")
    config.addinivalue_line("markers", "network: CNI / DNS / connectivity failure tests")
    config.addinivalue_line("markers", "scheduling: Pod scheduling failure tests")
    config.addinivalue_line("markers", "gpu: GPU isolation / device plugin failure tests")
    config.addinivalue_line("markers", "resource: Resource exhaustion / eviction tests")
    
    # Monitoring pre-mortem categories (DP:ETG)
    config.addinivalue_line("markers", "service_availability: Service availability tests")
    config.addinivalue_line("markers", "metrics_collection: Metrics collection tests")
    config.addinivalue_line("markers", "data_integrity: Data integrity tests")
    config.addinivalue_line("markers", "alerting: Alerting configuration tests")
    config.addinivalue_line("markers", "dashboard: Dashboard configuration tests")
    config.addinivalue_line("markers", "resource_exhaustion: Resource exhaustion tests")
    
    # Component-specific markers
    config.addinivalue_line("markers", "gpu_metrics: GPU metrics tests")
    config.addinivalue_line("markers", "power_metrics: Power metrics tests")
    
    # K8s Probe pre-mortem categories (DP:ETG)
    config.addinivalue_line("markers", "k8s_probe: K8s Probe MCP tests")
    config.addinivalue_line("markers", "connection: MCP connection failure tests")
    config.addinivalue_line("markers", "node_control: Node cordon/drain tests")
    config.addinivalue_line("markers", "workload: Pod scheduling/consolidation tests")
    config.addinivalue_line("markers", "metrics: Cluster metrics tests")
    config.addinivalue_line("markers", "permission: RBAC/permission tests")
    config.addinivalue_line("markers", "state: State consistency tests")
    
    # Hardware Safety tests (PRIORITY 0)
    config.addinivalue_line("markers", "safety: Hardware safety tests (PRIORITY 0)")
    
    # Workload Generation tests (F10.5 Track A)
    config.addinivalue_line("markers", "workload_gen: Workload generation tests")
    
    # Experiment Framework tests (F10.5 Track B)
    config.addinivalue_line("markers", "experiment: Experiment framework tests")

@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent.parent

@pytest.fixture
def terraform_dir(project_root: Path) -> Path:
    return project_root / "terraform"

@pytest.fixture
def run_command():
    def _run_command(cmd: list[str], cwd: Path | None = None, check: bool = True,
                     capture_output: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
        logger.info(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=cwd, check=check, capture_output=capture_output,
                              text=True, timeout=timeout)
    return _run_command

@pytest.fixture
def check_hugepages() -> dict[str, Any]:
    result = {"total_pages": 0, "free_pages": 0, "page_size_kb": 0,
              "total_memory_gb": 0, "free_memory_gb": 0, "errors": []}
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text().split("\n"):
                if line.startswith("HugePages_Total:"):
                    result["total_pages"] = int(line.split()[1])
                elif line.startswith("HugePages_Free:"):
                    result["free_pages"] = int(line.split()[1])
                elif line.startswith("Hugepagesize:"):
                    result["page_size_kb"] = int(line.split()[1])
            page_size_gb = result["page_size_kb"] / (1024 * 1024)
            result["total_memory_gb"] = result["total_pages"] * page_size_gb
            result["free_memory_gb"] = result["free_pages"] * page_size_gb
    except Exception as e:
        result["errors"].append(str(e))
    return result

@pytest.fixture
def check_packages(run_command) -> dict[str, Any]:
    packages = ["qemu-kvm", "libvirt-daemon", "libvirt-clients", "virtinst", "openvswitch-switch"]
    result = {"installed": [], "missing": [], "errors": []}
    for pkg in packages:
        try:
            r = run_command(["dpkg", "-s", pkg], capture_output=True, check=False)
            if r.returncode == 0:
                result["installed"].append(pkg)
            else:
                result["missing"].append(pkg)
        except Exception as e:
            result["errors"].append(f"{pkg}: {e}")
    return result

@pytest.fixture
def skip_unless_host():
    def _skip(reason: str = "Test requires Bizon host"):
        import os
        if "bizon" not in os.environ.get("HOSTNAME", "").lower():
            pytest.skip(reason)
    return _skip
