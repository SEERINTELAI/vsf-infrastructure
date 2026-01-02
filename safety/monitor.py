"""
Hardware Safety Monitor

Provides pre-flight checks, runtime monitoring, and emergency stop.
PRIORITY 0 - This module must be used for all workload generation.
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from .constraints import SafetyConstraints, DEFAULT_CONSTRAINTS

logger = logging.getLogger(__name__)


class SafetyAction(str, Enum):
    """Actions to take based on safety check results."""
    PROCEED = "proceed"           # Safe to continue
    WAIT_COOLDOWN = "wait"        # Wait for cooldown
    REDUCE_INTENSITY = "reduce"   # Reduce workload intensity
    ABORT = "abort"               # Stop all workloads immediately


class HardwareSafetyException(Exception):
    """Raised when a critical safety condition is detected."""
    pass


@dataclass
class SafetyResult:
    """Result of a safety check."""
    safe: bool
    action: SafetyAction
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metrics: dict[str, Any] = field(default_factory=dict)
    
    def __bool__(self) -> bool:
        return self.safe


@dataclass
class HardwareMetrics:
    """Current hardware metrics."""
    timestamp: datetime
    gpu_temps: dict[int, float] = field(default_factory=dict)  # GPU ID -> temp °C
    gpu_power: dict[int, float] = field(default_factory=dict)  # GPU ID -> watts
    total_power: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    
    @property
    def max_gpu_temp(self) -> float:
        return max(self.gpu_temps.values()) if self.gpu_temps else 0.0
    
    @property
    def total_gpu_power(self) -> float:
        return sum(self.gpu_power.values())


class HardwareSafetyMonitor:
    """
    Hardware safety monitor for VSF workloads.
    
    Usage:
        monitor = HardwareSafetyMonitor()
        
        # Before starting any workload
        result = await monitor.pre_flight_check()
        if not result.safe:
            logger.error(f"Cannot start: {result.reason}")
            return
        
        # During workload
        await monitor.start_runtime_monitoring()
        try:
            # ... run workload ...
        finally:
            await monitor.stop_runtime_monitoring()
    """
    
    def __init__(
        self,
        constraints: SafetyConstraints = DEFAULT_CONSTRAINTS,
        probe_endpoint: str | None = None
    ):
        self.constraints = constraints
        self.probe_endpoint = probe_endpoint
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._on_warning_callbacks: list[Callable] = []
        self._on_critical_callbacks: list[Callable] = []
    
    # =========================================================================
    # Metric Collection
    # =========================================================================
    
    async def _get_gpu_metrics(self) -> tuple[dict[int, float], dict[int, float]]:
        """Get GPU temperatures and power via nvidia-smi."""
        temps = {}
        power = {}
        
        try:
            # Query GPU temps
            result = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=index,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            if result.returncode == 0:
                for line in stdout.decode().strip().split("\n"):
                    if line:
                        parts = line.split(",")
                        if len(parts) >= 3:
                            gpu_id = int(parts[0].strip())
                            temp = float(parts[1].strip())
                            pwr = float(parts[2].strip())
                            temps[gpu_id] = temp
                            power[gpu_id] = pwr
        except Exception as e:
            logger.warning(f"Could not get GPU metrics: {e}")
        
        return temps, power
    
    async def _get_system_power(self) -> float:
        """Get total system power via RAPL or estimation."""
        try:
            # Try RAPL first
            import os
            rapl_path = "/sys/class/powercap/intel-rapl"
            if os.path.exists(rapl_path):
                total_power = 0.0
                for domain in os.listdir(rapl_path):
                    if domain.startswith("intel-rapl:"):
                        energy_path = f"{rapl_path}/{domain}/energy_uj"
                        if os.path.exists(energy_path):
                            with open(energy_path) as f:
                                energy1 = int(f.read().strip())
                            await asyncio.sleep(0.5)
                            with open(energy_path) as f:
                                energy2 = int(f.read().strip())
                            power = (energy2 - energy1) / 500000.0
                            total_power += power
                return total_power
        except Exception as e:
            logger.debug(f"Could not read RAPL: {e}")
        
        return 0.0
    
    async def _get_cpu_memory_percent(self) -> tuple[float, float]:
        """Get CPU and memory utilization."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5), psutil.virtual_memory().percent
        except ImportError:
            return 0.0, 0.0
    
    async def collect_metrics(self) -> HardwareMetrics:
        """Collect all hardware metrics."""
        gpu_temps, gpu_power = await self._get_gpu_metrics()
        cpu_power = await self._get_system_power()
        cpu_percent, mem_percent = await self._get_cpu_memory_percent()
        
        total_power = cpu_power + sum(gpu_power.values())
        
        return HardwareMetrics(
            timestamp=datetime.now(),
            gpu_temps=gpu_temps,
            gpu_power=gpu_power,
            total_power=total_power,
            cpu_percent=cpu_percent,
            memory_percent=mem_percent
        )
    
    # =========================================================================
    # Safety Checks
    # =========================================================================
    
    def _evaluate_safety(self, metrics: HardwareMetrics) -> SafetyResult:
        """Evaluate metrics against safety constraints."""
        c = self.constraints
        
        # Check GPU temperatures
        for gpu_id, temp in metrics.gpu_temps.items():
            if temp >= c.gpu_temp_critical:
                return SafetyResult(
                    safe=False,
                    action=SafetyAction.ABORT,
                    reason=f"CRITICAL: GPU {gpu_id} at {temp}°C (limit: {c.gpu_temp_critical}°C)",
                    metrics={"gpu_temps": metrics.gpu_temps}
                )
            if temp >= c.gpu_temp_warning:
                return SafetyResult(
                    safe=False,
                    action=SafetyAction.WAIT_COOLDOWN,
                    reason=f"WARNING: GPU {gpu_id} at {temp}°C (warning: {c.gpu_temp_warning}°C)",
                    metrics={"gpu_temps": metrics.gpu_temps}
                )
        
        # Check per-GPU power
        for gpu_id, power in metrics.gpu_power.items():
            if power >= c.per_gpu_power_critical:
                return SafetyResult(
                    safe=False,
                    action=SafetyAction.ABORT,
                    reason=f"CRITICAL: GPU {gpu_id} at {power}W (limit: {c.per_gpu_power_critical}W)",
                    metrics={"gpu_power": metrics.gpu_power}
                )
        
        # Check total power
        if metrics.total_power >= c.power_critical:
            return SafetyResult(
                safe=False,
                action=SafetyAction.ABORT,
                reason=f"CRITICAL: Total power {metrics.total_power}W (limit: {c.power_critical}W)",
                metrics={"total_power": metrics.total_power}
            )
        if metrics.total_power >= c.power_warning:
            return SafetyResult(
                safe=False,
                action=SafetyAction.REDUCE_INTENSITY,
                reason=f"WARNING: Total power {metrics.total_power}W (warning: {c.power_warning}W)",
                metrics={"total_power": metrics.total_power}
            )
        
        # Check resource utilization
        if metrics.cpu_percent >= c.max_cpu_percent:
            return SafetyResult(
                safe=False,
                action=SafetyAction.REDUCE_INTENSITY,
                reason=f"WARNING: CPU at {metrics.cpu_percent}% (limit: {c.max_cpu_percent}%)",
                metrics={"cpu_percent": metrics.cpu_percent}
            )
        
        if metrics.memory_percent >= c.max_memory_percent:
            return SafetyResult(
                safe=False,
                action=SafetyAction.REDUCE_INTENSITY,
                reason=f"WARNING: Memory at {metrics.memory_percent}% (limit: {c.max_memory_percent}%)",
                metrics={"memory_percent": metrics.memory_percent}
            )
        
        # All checks passed
        return SafetyResult(
            safe=True,
            action=SafetyAction.PROCEED,
            reason="All safety checks passed",
            metrics={
                "max_gpu_temp": metrics.max_gpu_temp,
                "total_power": metrics.total_power,
                "cpu_percent": metrics.cpu_percent,
                "memory_percent": metrics.memory_percent
            }
        )
    
    async def pre_flight_check(self) -> SafetyResult:
        """
        Pre-flight safety check before starting any workload.
        
        MUST be called before any workload generation.
        
        Returns:
            SafetyResult with go/no-go decision
        """
        logger.info("Running pre-flight safety check...")
        
        try:
            metrics = await self.collect_metrics()
            result = self._evaluate_safety(metrics)
            
            if result.safe:
                logger.info(f"Pre-flight check PASSED: {result.reason}")
            else:
                logger.warning(f"Pre-flight check FAILED: {result.reason}")
            
            return result
            
        except Exception as e:
            logger.error(f"Pre-flight check ERROR: {e}")
            # Be conservative on errors
            return SafetyResult(
                safe=False,
                action=SafetyAction.ABORT,
                reason=f"Pre-flight check failed with error: {e}"
            )
    
    # =========================================================================
    # Runtime Monitoring
    # =========================================================================
    
    def on_warning(self, callback: Callable[[SafetyResult], None]):
        """Register callback for warning conditions."""
        self._on_warning_callbacks.append(callback)
    
    def on_critical(self, callback: Callable[[SafetyResult], None]):
        """Register callback for critical conditions."""
        self._on_critical_callbacks.append(callback)
    
    async def _monitor_loop(self):
        """Runtime monitoring loop."""
        while self._monitoring:
            try:
                metrics = await self.collect_metrics()
                result = self._evaluate_safety(metrics)
                
                if result.action == SafetyAction.ABORT:
                    logger.critical(f"SAFETY CRITICAL: {result.reason}")
                    for callback in self._on_critical_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            logger.error(f"Critical callback failed: {e}")
                    
                    # Trigger emergency stop
                    await self.emergency_stop()
                    raise HardwareSafetyException(result.reason)
                
                elif result.action == SafetyAction.REDUCE_INTENSITY:
                    logger.warning(f"SAFETY WARNING: {result.reason}")
                    for callback in self._on_warning_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            logger.error(f"Warning callback failed: {e}")
                
            except HardwareSafetyException:
                raise
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            await asyncio.sleep(self.constraints.runtime_check_interval)
    
    async def start_runtime_monitoring(self):
        """Start runtime safety monitoring."""
        if self._monitoring:
            return
        
        logger.info("Starting runtime safety monitoring")
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def stop_runtime_monitoring(self):
        """Stop runtime safety monitoring."""
        if not self._monitoring:
            return
        
        logger.info("Stopping runtime safety monitoring")
        self._monitoring = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
    
    # =========================================================================
    # Emergency Stop
    # =========================================================================
    
    async def emergency_stop(self):
        """
        Emergency stop all workloads.
        
        Immediately terminates all generated workloads.
        Does NOT wait for graceful termination.
        """
        logger.critical("🚨 EMERGENCY STOP ACTIVATED 🚨")
        
        try:
            # Kill all workload pods
            await asyncio.create_subprocess_exec(
                "kubectl", "delete", "pods",
                "-l", "vsf-workload=true",
                "--force", "--grace-period=0",
                "--all-namespaces",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Scale all workload deployments to 0
            await asyncio.create_subprocess_exec(
                "kubectl", "scale", "deployment",
                "-l", "vsf-workload=true",
                "--replicas=0",
                "--all-namespaces",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            logger.critical("Emergency stop completed - all workloads terminated")
            
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}")
            raise


# =============================================================================
# Context Manager for Safe Workload Execution
# =============================================================================

class SafeWorkloadContext:
    """
    Context manager for safe workload execution.
    
    Usage:
        async with SafeWorkloadContext() as ctx:
            if ctx.safe:
                # Run workload
                ...
    """
    
    def __init__(
        self,
        constraints: SafetyConstraints = DEFAULT_CONSTRAINTS,
        on_warning: Callable | None = None
    ):
        self.monitor = HardwareSafetyMonitor(constraints)
        self.safe = False
        self._on_warning = on_warning
    
    async def __aenter__(self):
        # Pre-flight check
        result = await self.monitor.pre_flight_check()
        self.safe = result.safe
        
        if not self.safe:
            logger.error(f"Workload blocked by safety check: {result.reason}")
            return self
        
        # Register warning callback
        if self._on_warning:
            self.monitor.on_warning(self._on_warning)
        
        # Start monitoring
        await self.monitor.start_runtime_monitoring()
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.monitor.stop_runtime_monitoring()
        
        if exc_type is HardwareSafetyException:
            logger.critical(f"Workload terminated by safety monitor: {exc_val}")
            return False  # Re-raise
        
        return False
