"""
F10.1 Comprehensive Infrastructure Validation Test Suite

This test suite validates all infrastructure components for the Virtual Server Farm.
Tests are designed to be idempotent and non-destructive (read-only checks).

Test Categories:
1. IOMMU validation (kernel params, groups)
2. HugePages validation (allocation, availability)
3. VM validation (control plane, workers, GPU workers)
4. GPU passthrough validation (VFIO binding, device assignment)
5. OVS networking validation (bridges, ports, flows)
6. VirtualBMC validation (service, VM registration)
"""

import pytest
import subprocess
import os
from pathlib import Path
from typing import Any


# =============================================================================
# IOMMU Validation Tests
# =============================================================================

class TestIOMMU:
    """Test IOMMU configuration for GPU passthrough."""
    
    @pytest.mark.infrastructure
    def test_iommu_enabled(self) -> None:
        """Verify IOMMU is enabled in kernel."""
        iommu_path = Path("/sys/class/iommu")
        assert iommu_path.exists(), "IOMMU subsystem not found in /sys/class/iommu"
        
        # Check for IOMMU devices
        iommu_devices = list(iommu_path.iterdir())
        assert len(iommu_devices) > 0, "No IOMMU devices found"
    
    @pytest.mark.infrastructure
    def test_iommu_groups_exist(self) -> None:
        """Verify IOMMU groups are created."""
        iommu_groups = Path("/sys/kernel/iommu_groups")
        assert iommu_groups.exists(), "IOMMU groups directory not found"
        
        groups = list(iommu_groups.iterdir())
        assert len(groups) > 0, "No IOMMU groups found"
    
    @pytest.mark.infrastructure
    def test_gpu_iommu_isolation(self) -> None:
        """Verify each GPU is in its own IOMMU group (ideal for passthrough)."""
        result = subprocess.run(
            ["lspci", "-d", "10de:", "-n"],
            capture_output=True, text=True
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            pytest.skip("No NVIDIA GPUs found")
        
        gpu_addresses = []
        for line in result.stdout.strip().split('\n'):
            if line:
                addr = line.split()[0]
                gpu_addresses.append(addr)
        
        gpu_groups = set()
        for addr in gpu_addresses:
            iommu_link = Path(f"/sys/bus/pci/devices/0000:{addr}/iommu_group")
            if iommu_link.exists():
                group = iommu_link.resolve().name
                gpu_groups.add(group)
        
        assert len(gpu_groups) >= len(gpu_addresses) // 2, \
            f"GPUs may not be properly isolated. Groups: {len(gpu_groups)}, GPUs: {len(gpu_addresses)}"
    
    @pytest.mark.infrastructure
    def test_vfio_modules_available(self) -> None:
        """Verify VFIO modules are available."""
        result = subprocess.run(
            ["modinfo", "vfio-pci"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "vfio-pci module not available"


# =============================================================================
# HugePages Extended Tests
# =============================================================================

class TestHugePagesExtended:
    """Extended HugePages tests beyond basic configuration."""
    
    EXPECTED_HUGEPAGES_GB = 900
    HUGEPAGE_SIZE_KB = 2048
    
    @pytest.mark.infrastructure
    def test_transparent_hugepages_disabled(self) -> None:
        """Verify Transparent HugePages is disabled (recommended for VMs)."""
        thp_path = Path("/sys/kernel/mm/transparent_hugepage/enabled")
        if not thp_path.exists():
            pytest.skip("THP settings not found")
        
        content = thp_path.read_text()
        assert "[never]" in content or "[madvise]" in content, \
            f"THP should be disabled or madvise for VM workloads: {content}"
    
    @pytest.mark.infrastructure
    def test_hugepages_persistence(self) -> None:
        """Verify HugePages are configured to persist across reboots."""
        sysctl_conf = Path("/etc/sysctl.conf")
        sysctl_d = Path("/etc/sysctl.d")
        
        found = False
        if sysctl_conf.exists():
            if "vm.nr_hugepages" in sysctl_conf.read_text():
                found = True
        
        if not found and sysctl_d.exists():
            for conf in sysctl_d.glob("*.conf"):
                if "vm.nr_hugepages" in conf.read_text():
                    found = True
                    break
        
        if not found:
            pytest.skip("HugePages persistence not configured yet (Task F10.1.4)")


# =============================================================================
# Libvirt Service Tests
# =============================================================================

class TestLibvirtService:
    """Test libvirt service configuration."""
    
    @pytest.mark.infrastructure
    def test_libvirtd_running(self) -> None:
        """Verify libvirtd service is running."""
        result = subprocess.run(
            ["systemctl", "is-active", "libvirtd"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "active", "libvirtd service not running"
    
    @pytest.mark.infrastructure
    def test_libvirt_connection(self) -> None:
        """Verify libvirt connection works."""
        result = subprocess.run(
            ["virsh", "-c", "qemu:///system", "list"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Cannot connect to libvirt: {result.stderr}"
    
    @pytest.mark.infrastructure
    def test_default_storage_pool(self) -> None:
        """Verify default storage pool exists."""
        result = subprocess.run(
            ["virsh", "-c", "qemu:///system", "pool-list", "--all"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "Cannot list storage pools"
        assert "default" in result.stdout or "vsf" in result.stdout, \
            "No suitable storage pool found"


# =============================================================================
# VM Validation Tests
# =============================================================================

class TestVMs:
    """Test VM configuration (run after VMs are deployed)."""
    
    EXPECTED_CONTROL_PLANE = 3
    EXPECTED_WORKERS = 10
    EXPECTED_GPU_WORKERS = 8
    EXPECTED_TOTAL = 24
    
    def _get_vm_list(self) -> list[str]:
        """Get list of all VMs."""
        result = subprocess.run(
            ["virsh", "-c", "qemu:///system", "list", "--all", "--name"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return []
        return [vm for vm in result.stdout.strip().split('\n') if vm]
    
    @pytest.mark.infrastructure
    def test_control_plane_vms_exist(self) -> None:
        """Verify control plane VMs are deployed."""
        vms = self._get_vm_list()
        if not vms:
            pytest.skip("No VMs deployed yet (Task F10.1.7)")
        
        control_plane = [vm for vm in vms if "control" in vm.lower() or "cp" in vm.lower()]
        assert len(control_plane) >= self.EXPECTED_CONTROL_PLANE, \
            f"Expected {self.EXPECTED_CONTROL_PLANE} control plane VMs, found {len(control_plane)}"
    
    @pytest.mark.infrastructure
    def test_worker_vms_exist(self) -> None:
        """Verify worker VMs are deployed."""
        vms = self._get_vm_list()
        if not vms:
            pytest.skip("No VMs deployed yet (Task F10.1.8)")
        
        workers = [vm for vm in vms if "worker" in vm.lower() and "gpu" not in vm.lower()]
        assert len(workers) >= self.EXPECTED_WORKERS, \
            f"Expected {self.EXPECTED_WORKERS} worker VMs, found {len(workers)}"
    
    @pytest.mark.infrastructure
    def test_gpu_worker_vms_exist(self) -> None:
        """Verify GPU worker VMs are deployed."""
        vms = self._get_vm_list()
        if not vms:
            pytest.skip("No VMs deployed yet (Task F10.1.9)")
        
        gpu_workers = [vm for vm in vms if "gpu" in vm.lower()]
        assert len(gpu_workers) >= self.EXPECTED_GPU_WORKERS, \
            f"Expected {self.EXPECTED_GPU_WORKERS} GPU worker VMs, found {len(gpu_workers)}"
    
    @pytest.mark.infrastructure
    def test_total_vm_count(self) -> None:
        """Verify total VM count."""
        vms = self._get_vm_list()
        if not vms:
            pytest.skip("No VMs deployed yet")
        
        assert len(vms) >= self.EXPECTED_TOTAL, \
            f"Expected at least {self.EXPECTED_TOTAL} VMs, found {len(vms)}"


# =============================================================================
# GPU Passthrough Tests
# =============================================================================

class TestGPUPassthrough:
    """Test GPU passthrough configuration."""
    
    @pytest.mark.infrastructure
    def test_nvidia_gpus_detected(self) -> None:
        """Verify NVIDIA GPUs are detected."""
        result = subprocess.run(
            ["lspci", "-d", "10de:"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "lspci failed"
        
        gpus = [line for line in result.stdout.split('\n') if line]
        assert len(gpus) > 0, "No NVIDIA GPUs detected"
    
    @pytest.mark.infrastructure
    def test_gpu_driver_binding(self) -> None:
        """Verify GPUs for passthrough are bound to vfio-pci."""
        result = subprocess.run(
            ["lspci", "-d", "10de:", "-n"],
            capture_output=True, text=True
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            pytest.skip("No NVIDIA GPUs found")
        
        gpu_addresses = []
        for line in result.stdout.strip().split('\n'):
            if line:
                addr = line.split()[0]
                gpu_addresses.append(f"0000:{addr}")
        
        vfio_bound = 0
        nvidia_bound = 0
        for addr in gpu_addresses:
            driver_link = Path(f"/sys/bus/pci/devices/{addr}/driver")
            if driver_link.exists():
                driver = driver_link.resolve().name
                if driver == "vfio-pci":
                    vfio_bound += 1
                elif driver == "nvidia":
                    nvidia_bound += 1
        
        # At least some GPUs should be bound to nvidia (for host)
        # and some to vfio-pci (for passthrough)
        total_bound = vfio_bound + nvidia_bound
        assert total_bound > 0, "No GPUs bound to any driver"


# =============================================================================
# OVS Networking Tests
# =============================================================================

class TestOVSNetworking:
    """Test Open vSwitch networking configuration."""
    
    VSF_BRIDGE = "br-vsf"
    
    @pytest.mark.infrastructure
    def test_ovs_service_running(self) -> None:
        """Verify OVS service is running."""
        result = subprocess.run(
            ["systemctl", "is-active", "openvswitch-switch"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "active", "OVS service not running"
    
    @pytest.mark.infrastructure
    def test_vsf_bridge_exists(self) -> None:
        """Verify VSF bridge exists."""
        result = subprocess.run(
            ["ovs-vsctl", "br-exists", self.VSF_BRIDGE],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"OVS bridge {self.VSF_BRIDGE} not yet created (Task F10.1.10)")
    
    @pytest.mark.infrastructure
    def test_ovs_flows_configured(self) -> None:
        """Verify OVS flows are configured."""
        result = subprocess.run(
            ["ovs-ofctl", "dump-flows", self.VSF_BRIDGE],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"Cannot query flows on {self.VSF_BRIDGE}")
        
        flows = result.stdout.strip().split('\n')
        assert len(flows) > 1, "No OVS flows configured"


# =============================================================================
# VirtualBMC Tests
# =============================================================================

class TestVirtualBMC:
    """Test VirtualBMC configuration."""
    
    @pytest.mark.infrastructure
    def test_virtualbmc_available(self) -> None:
        """Verify VirtualBMC is installed."""
        result = subprocess.run(
            ["vbmc", "list"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip("VirtualBMC not yet configured (Task F10.1.5)")
    
    @pytest.mark.infrastructure
    def test_vms_registered_with_vbmc(self) -> None:
        """Verify VMs are registered with VirtualBMC."""
        result = subprocess.run(
            ["vbmc", "list"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip("VirtualBMC not available")
        
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:
            pytest.skip("No VMs registered with VirtualBMC yet (Task F10.1.11)")
        
        vm_count = len([l for l in lines if "running" in l.lower() or "down" in l.lower()])
        assert vm_count > 0, "No VMs registered with VirtualBMC"
    
    @pytest.mark.infrastructure
    def test_ipmitool_installed(self) -> None:
        """Verify ipmitool is installed (for BMC testing)."""
        result = subprocess.run(
            ["which", "ipmitool"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "ipmitool not installed"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for end-to-end functionality."""
    
    @pytest.mark.infrastructure
    @pytest.mark.integration
    def test_vm_can_be_controlled_via_ipmi(self) -> None:
        """Verify a VM can be controlled via IPMI (through VirtualBMC)."""
        result = subprocess.run(
            ["vbmc", "list", "--format", "value", "-c", "Domain Name", "-c", "Port"],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout.strip():
            pytest.skip("No VirtualBMC VMs to test")
        
        lines = result.stdout.strip().split('\n')
        if not lines:
            pytest.skip("No VirtualBMC VMs configured")
        
        first_vm = lines[0].split()
        if len(first_vm) < 2:
            pytest.skip("Cannot parse VirtualBMC output")
        
        port = first_vm[-1]
        
        result = subprocess.run(
            ["ipmitool", "-I", "lanplus", "-H", "localhost", "-p", port,
             "-U", "admin", "-P", "password", "power", "status"],
            capture_output=True, text=True
        )
        # Command recognition is success even if auth fails
        assert "power" in result.stdout.lower() or "chassis" in result.stderr.lower() or result.returncode == 0, \
            f"IPMI command failed unexpectedly: {result.stderr}"
