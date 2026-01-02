"""
Hardware Safety Constraints

Defines the absolute limits for hardware safety.
These values are based on Bizon1 specifications:
- 8x NVIDIA GPUs
- 4kW power supply
- 1TB RAM
- 200 CPU threads
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyConstraints:
    """
    Immutable safety constraints.
    
    These are the ABSOLUTE LIMITS that must never be exceeded.
    """
    
    # Temperature limits (Celsius)
    gpu_temp_warning: int = 80
    gpu_temp_critical: int = 85  # HARD STOP
    cpu_temp_warning: int = 90
    cpu_temp_critical: int = 95  # HARD STOP
    
    # Power limits (Watts)
    power_warning: int = 2000
    power_critical: int = 2200  # HARD STOP
    per_gpu_power_warning: int = 250
    per_gpu_power_critical: int = 300  # HARD STOP
    
    # Resource limits (percentage)
    max_cpu_percent: float = 80.0
    max_memory_percent: float = 85.0
    max_gpu_memory_percent: float = 90.0
    
    # Workload limits
    max_intensity: float = 0.8  # 80% intensity cap
    max_pods: int = 100
    max_gpus_for_workloads: int = 6  # Reserve 2 for system
    
    # Monitoring intervals (seconds)
    runtime_check_interval: int = 10
    cooldown_wait_seconds: int = 60
    
    def validate(self) -> list[str]:
        """Validate constraints are sensible."""
        errors = []
        
        if self.gpu_temp_warning >= self.gpu_temp_critical:
            errors.append("GPU temp warning must be < critical")
        
        if self.power_warning >= self.power_critical:
            errors.append("Power warning must be < critical")
        
        if self.max_intensity > 1.0 or self.max_intensity < 0.1:
            errors.append("Max intensity must be between 0.1 and 1.0")
        
        if self.max_cpu_percent > 100 or self.max_cpu_percent < 10:
            errors.append("Max CPU percent must be between 10 and 100")
        
        return errors


# Default constraints - NEVER modify these without explicit approval
DEFAULT_CONSTRAINTS = SafetyConstraints()


# Bizon1-specific constraints (slightly more conservative)
BIZON1_CONSTRAINTS = SafetyConstraints(
    gpu_temp_warning=75,  # More conservative for 8-GPU system
    gpu_temp_critical=82,
    power_warning=1800,   # More conservative for 4kW PSU
    power_critical=2000,
    max_gpus_for_workloads=6,
)
