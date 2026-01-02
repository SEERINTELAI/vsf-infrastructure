"""
VSF Hardware Safety Module

PRIORITY 0 - Non-negotiable safety constraints for workload generation.

This module provides:
- Pre-flight safety checks before any workload starts
- Runtime monitoring during workload execution  
- Emergency stop procedures for critical conditions

Temperature Limits:
- GPU Warning: 80°C
- GPU HARD STOP: 85°C

Power Limits:
- Warning: 2000W
- HARD STOP: 2200W
"""

__version__ = "1.0.0"

from .monitor import (
    HardwareSafetyMonitor,
    SafetyResult,
    SafetyAction,
    HardwareSafetyException,
)
from .constraints import (
    SafetyConstraints,
    DEFAULT_CONSTRAINTS,
)

__all__ = [
    "HardwareSafetyMonitor",
    "SafetyResult",
    "SafetyAction",
    "HardwareSafetyException",
    "SafetyConstraints",
    "DEFAULT_CONSTRAINTS",
]
