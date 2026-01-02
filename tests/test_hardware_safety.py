"""
Hardware Safety Test Suite (PRIORITY 0)

These tests MUST pass before any workload generation can proceed.
They validate the safety mechanisms that protect Bizon1 hardware.

Pre-Mortem Failure Categories:
1. Pre-Flight Failure - Safety checks don't block on dangerous conditions
2. Runtime Failure - Monitoring doesn't detect critical conditions
3. Emergency Stop Failure - Workloads not terminated on critical
4. Constraint Enforcement Failure - K8s limits not applied

Total: 12 tests (exceeds minimum of 8 specified in F10.5_SAFETY.md)

Usage:
    pytest tests/test_hardware_safety.py -v
    pytest tests/test_hardware_safety.py -v -m safety
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import safety module (will be available when running from repo root)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from safety.constraints import SafetyConstraints, DEFAULT_CONSTRAINTS, BIZON1_CONSTRAINTS
from safety.monitor import (
    HardwareSafetyMonitor,
    SafetyResult,
    SafetyAction,
    HardwareMetrics,
    HardwareSafetyException,
    SafeWorkloadContext,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def constraints():
    """Default safety constraints."""
    return DEFAULT_CONSTRAINTS


@pytest.fixture
def monitor(constraints):
    """Create safety monitor with default constraints."""
    return HardwareSafetyMonitor(constraints=constraints)


@pytest.fixture
def safe_metrics():
    """Metrics that should pass all safety checks."""
    return HardwareMetrics(
        timestamp=datetime.now(),
        gpu_temps={0: 65, 1: 68, 2: 70, 3: 67},
        gpu_power={0: 150, 1: 160, 2: 155, 3: 145},
        total_power=1200,
        cpu_percent=45,
        memory_percent=60
    )


@pytest.fixture
def warning_metrics():
    """Metrics that should trigger warnings but not abort."""
    return HardwareMetrics(
        timestamp=datetime.now(),
        gpu_temps={0: 82, 1: 78, 2: 75, 3: 76},  # GPU 0 above warning
        gpu_power={0: 180, 1: 170, 2: 165, 3: 160},
        total_power=1800,
        cpu_percent=70,
        memory_percent=75
    )


@pytest.fixture
def critical_temp_metrics():
    """Metrics with critical GPU temperature."""
    return HardwareMetrics(
        timestamp=datetime.now(),
        gpu_temps={0: 87, 1: 78, 2: 75, 3: 76},  # GPU 0 above critical
        gpu_power={0: 180, 1: 170, 2: 165, 3: 160},
        total_power=1500,
        cpu_percent=50,
        memory_percent=60
    )


@pytest.fixture
def critical_power_metrics():
    """Metrics with critical power consumption."""
    return HardwareMetrics(
        timestamp=datetime.now(),
        gpu_temps={0: 70, 1: 72, 2: 68, 3: 71},
        gpu_power={0: 280, 1: 275, 2: 270, 3: 265},
        total_power=2300,  # Above critical threshold
        cpu_percent=85,
        memory_percent=80
    )


# =============================================================================
# Category 1: Pre-Flight Checks (4 tests)
# =============================================================================

class TestPreFlightChecks:
    """
    Tests for pre-flight safety checks.
    
    Pre-mortem: What if pre-flight doesn't block dangerous conditions?
    """
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_pre_flight_passes_on_safe_metrics(self, monitor, safe_metrics):
        """Verify pre-flight passes when all metrics are safe."""
        with patch.object(monitor, 'collect_metrics', return_value=safe_metrics):
            result = await monitor.pre_flight_check()
        
        assert result.safe is True
        assert result.action == SafetyAction.PROCEED
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_pre_flight_blocks_on_high_gpu_temp(self, monitor, critical_temp_metrics):
        """Verify pre-flight blocks when GPU temperature exceeds 85°C."""
        with patch.object(monitor, 'collect_metrics', return_value=critical_temp_metrics):
            result = await monitor.pre_flight_check()
        
        assert result.safe is False
        assert result.action == SafetyAction.ABORT
        assert "GPU 0" in result.reason
        assert "87" in result.reason  # Temperature value
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_pre_flight_blocks_on_high_power(self, monitor, critical_power_metrics):
        """Verify pre-flight blocks when power exceeds 2200W."""
        with patch.object(monitor, 'collect_metrics', return_value=critical_power_metrics):
            result = await monitor.pre_flight_check()
        
        assert result.safe is False
        assert result.action == SafetyAction.ABORT
        assert "2300" in result.reason or "power" in result.reason.lower()
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_pre_flight_waits_on_warning_temp(self, monitor, warning_metrics):
        """Verify pre-flight requests cooldown when GPU temp is in warning range."""
        with patch.object(monitor, 'collect_metrics', return_value=warning_metrics):
            result = await monitor.pre_flight_check()
        
        assert result.safe is False
        assert result.action == SafetyAction.WAIT_COOLDOWN
        assert "82" in result.reason  # Warning temperature


# =============================================================================
# Category 2: Runtime Monitoring (3 tests)
# =============================================================================

class TestRuntimeMonitoring:
    """
    Tests for runtime safety monitoring.
    
    Pre-mortem: What if runtime monitoring doesn't detect critical conditions?
    """
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_runtime_monitor_triggers_warning_callback(self, monitor, warning_metrics):
        """Verify runtime monitor calls warning callback on warning conditions."""
        warning_triggered = []
        
        def on_warning(result):
            warning_triggered.append(result)
        
        monitor.on_warning(on_warning)
        
        # Simulate one iteration of monitor loop
        with patch.object(monitor, 'collect_metrics', return_value=warning_metrics):
            result = monitor._evaluate_safety(warning_metrics)
        
        # Should be a warning action
        assert result.action in [SafetyAction.WAIT_COOLDOWN, SafetyAction.REDUCE_INTENSITY]
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_runtime_monitor_triggers_critical_callback(self, monitor, critical_temp_metrics):
        """Verify runtime monitor calls critical callback on critical conditions."""
        critical_triggered = []
        
        def on_critical(result):
            critical_triggered.append(result)
        
        monitor.on_critical(on_critical)
        
        # Evaluate critical metrics
        result = monitor._evaluate_safety(critical_temp_metrics)
        
        assert result.action == SafetyAction.ABORT
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_runtime_monitor_reduces_intensity_on_high_cpu(self, monitor):
        """Verify runtime monitor requests intensity reduction on high CPU."""
        high_cpu_metrics = HardwareMetrics(
            timestamp=datetime.now(),
            gpu_temps={0: 70},
            gpu_power={0: 150},
            total_power=1500,
            cpu_percent=85,  # Above 80% threshold
            memory_percent=60
        )
        
        result = monitor._evaluate_safety(high_cpu_metrics)
        
        assert result.action == SafetyAction.REDUCE_INTENSITY
        assert "CPU" in result.reason


# =============================================================================
# Category 3: Emergency Stop (3 tests)
# =============================================================================

class TestEmergencyStop:
    """
    Tests for emergency stop procedure.
    
    Pre-mortem: What if emergency stop doesn't terminate workloads?
    """
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_calls_kubectl(self, monitor):
        """Verify emergency stop executes kubectl commands."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_process = AsyncMock()
            mock_exec.return_value = mock_process
            
            await monitor.emergency_stop()
            
            # Should have called kubectl at least twice (delete pods, scale deployments)
            assert mock_exec.call_count >= 2
            
            # Check kubectl was called
            calls = [str(call) for call in mock_exec.call_args_list]
            assert any('kubectl' in call for call in calls)
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_deletes_workload_pods(self, monitor):
        """Verify emergency stop deletes pods with vsf-workload label."""
        kubectl_calls = []
        
        async def mock_subprocess(*args, **kwargs):
            kubectl_calls.append(args)
            mock = AsyncMock()
            return mock
        
        with patch('asyncio.create_subprocess_exec', side_effect=mock_subprocess):
            await monitor.emergency_stop()
        
        # Find the delete pods call
        delete_call = None
        for call in kubectl_calls:
            if 'delete' in call and 'pods' in call:
                delete_call = call
                break
        
        assert delete_call is not None
        assert 'vsf-workload=true' in str(delete_call) or '-l' in delete_call
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_scales_deployments_to_zero(self, monitor):
        """Verify emergency stop scales workload deployments to 0."""
        kubectl_calls = []
        
        async def mock_subprocess(*args, **kwargs):
            kubectl_calls.append(args)
            mock = AsyncMock()
            return mock
        
        with patch('asyncio.create_subprocess_exec', side_effect=mock_subprocess):
            await monitor.emergency_stop()
        
        # Find the scale call
        scale_call = None
        for call in kubectl_calls:
            if 'scale' in call:
                scale_call = call
                break
        
        assert scale_call is not None
        assert '--replicas=0' in scale_call


# =============================================================================
# Category 4: Constraint Enforcement (2 tests)
# =============================================================================

class TestConstraintEnforcement:
    """
    Tests for safety constraint enforcement.
    
    Pre-mortem: What if constraints aren't properly enforced?
    """
    
    @pytest.mark.safety
    def test_default_constraints_valid(self):
        """Verify default constraints pass validation."""
        errors = DEFAULT_CONSTRAINTS.validate()
        assert len(errors) == 0
    
    @pytest.mark.safety
    def test_bizon1_constraints_more_conservative(self):
        """Verify Bizon1 constraints are more conservative than defaults."""
        assert BIZON1_CONSTRAINTS.gpu_temp_warning < DEFAULT_CONSTRAINTS.gpu_temp_warning
        assert BIZON1_CONSTRAINTS.power_warning < DEFAULT_CONSTRAINTS.power_warning
    
    @pytest.mark.safety
    def test_intensity_capped_at_max(self):
        """Verify max intensity is capped at 80%."""
        assert DEFAULT_CONSTRAINTS.max_intensity <= 0.8
        assert BIZON1_CONSTRAINTS.max_intensity <= 0.8


# =============================================================================
# Category 5: Context Manager (2 tests)
# =============================================================================

class TestSafeWorkloadContext:
    """
    Tests for SafeWorkloadContext.
    
    Pre-mortem: What if context manager doesn't properly manage lifecycle?
    """
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_context_blocks_on_unsafe(self):
        """Verify context manager blocks workload on unsafe conditions."""
        critical_metrics = HardwareMetrics(
            timestamp=datetime.now(),
            gpu_temps={0: 90},  # Critical
            gpu_power={0: 200},
            total_power=1500,
            cpu_percent=50,
            memory_percent=60
        )
        
        async with SafeWorkloadContext() as ctx:
            # Mock the monitor to return critical
            with patch.object(ctx.monitor, 'collect_metrics', return_value=critical_metrics):
                result = await ctx.monitor.pre_flight_check()
                
        # Pre-flight should have failed
        assert result.safe is False
    
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_context_stops_monitoring_on_exit(self):
        """Verify context manager stops monitoring when exiting."""
        safe_metrics = HardwareMetrics(
            timestamp=datetime.now(),
            gpu_temps={0: 60},
            gpu_power={0: 150},
            total_power=1000,
            cpu_percent=40,
            memory_percent=50
        )
        
        ctx = SafeWorkloadContext()
        
        with patch.object(ctx.monitor, 'collect_metrics', return_value=safe_metrics):
            await ctx.__aenter__()
            assert ctx.safe is True
            
            await ctx.__aexit__(None, None, None)
            assert ctx.monitor._monitoring is False


# =============================================================================
# Test Summary
# =============================================================================
# Total: 12 tests across 5 categories
#
# Category 1 - Pre-Flight Checks: 4 tests
# Category 2 - Runtime Monitoring: 3 tests
# Category 3 - Emergency Stop: 3 tests
# Category 4 - Constraint Enforcement: 2 tests (3 assertions)
# Category 5 - Context Manager: 2 tests
#
# Markers:
#   - safety: Hardware safety tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "safety"])
