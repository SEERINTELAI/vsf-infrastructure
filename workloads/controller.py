"""
Workload Controller

Controls workload intensity and applies patterns over time.
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)


class WorkloadController:
    """
    Controls workload intensity and applies time-based patterns.
    
    Usage:
        controller = WorkloadController()
        await controller.scale("my-deployment", "vsf-workloads", replicas=5)
        await controller.apply_pattern("my-deployment", "vsf-workloads", "bursty", duration=300)
    """
    
    # Intensity patterns (normalized 0-1)
    PATTERNS = {
        "steady-state": lambda t, duration: 1.0,
        "bursty": lambda t, duration: 0.4 + 0.6 * (1 if (int(t / 30) % 2 == 0) else 0),
        "diurnal": lambda t, duration: 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t / duration)),
        "batch-gpu": lambda t, duration: 1.0,  # Full intensity for batch
        "mixed": lambda t, duration: 0.5 + 0.3 * math.sin(4 * math.pi * t / duration),
    }
    
    def __init__(
        self,
        kubeconfig: str | None = None,
        max_intensity: float = 0.8
    ):
        self.kubeconfig = kubeconfig
        self.max_intensity = max_intensity
        self._running = False
    
    def _clamp_intensity(self, value: float) -> float:
        """Clamp intensity to valid range."""
        return max(0.0, min(value, self.max_intensity))
    
    def get_intensity(self, pattern: str, elapsed: float, duration: float) -> float:
        """
        Get intensity value for a pattern at a given time.
        
        Args:
            pattern: Pattern name
            elapsed: Elapsed time in seconds
            duration: Total duration in seconds
            
        Returns:
            Intensity value 0.0 to max_intensity
        """
        pattern_fn = self.PATTERNS.get(pattern, self.PATTERNS["steady-state"])
        raw_intensity = pattern_fn(elapsed, duration)
        return self._clamp_intensity(raw_intensity)
    
    async def scale(
        self,
        deployment: str,
        namespace: str,
        replicas: int
    ) -> bool:
        """
        Scale a deployment to specified replicas.
        
        Args:
            deployment: Deployment name
            namespace: Namespace
            replicas: Target replica count
            
        Returns:
            True if successful
        """
        cmd = [
            "kubectl", "scale", "deployment", deployment,
            "-n", namespace,
            f"--replicas={replicas}"
        ]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        
        logger.info(f"Scaling {deployment} to {replicas} replicas")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.error(f"Scale failed: {stderr.decode()}")
            return False
        
        return True
    
    async def apply_pattern(
        self,
        deployment: str,
        namespace: str,
        pattern: str,
        base_replicas: int,
        duration: int,
        interval: int = 30,
        on_change: Callable[[float, int], None] | None = None
    ) -> None:
        """
        Apply an intensity pattern to a deployment.
        
        Args:
            deployment: Deployment name
            namespace: Namespace
            pattern: Pattern name
            base_replicas: Maximum replica count
            duration: Total duration in seconds
            interval: Interval between adjustments
            on_change: Optional callback(intensity, replicas)
        """
        logger.info(f"Starting pattern '{pattern}' for {deployment} ({duration}s)")
        
        self._running = True
        start = datetime.now()
        
        try:
            while self._running:
                elapsed = (datetime.now() - start).total_seconds()
                if elapsed >= duration:
                    break
                
                intensity = self.get_intensity(pattern, elapsed, duration)
                target_replicas = max(1, int(base_replicas * intensity))
                
                await self.scale(deployment, namespace, target_replicas)
                
                if on_change:
                    on_change(intensity, target_replicas)
                
                logger.debug(f"Pattern step: elapsed={elapsed:.0f}s, intensity={intensity:.2f}, replicas={target_replicas}")
                
                await asyncio.sleep(interval)
        
        finally:
            self._running = False
            logger.info(f"Pattern '{pattern}' completed for {deployment}")
    
    def stop(self):
        """Stop the running pattern."""
        self._running = False
