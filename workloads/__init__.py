"""
VSF Workload Generation Module

Generates K8s workloads for benchmarking and optimization experiments.
Integrated with Hardware Safety Monitor (PRIORITY 0).
"""

__version__ = "1.0.0"

from .generator import WorkloadGenerator
from .profiles import WorkloadProfile, load_profile, BUILTIN_PROFILES
from .controller import WorkloadController

__all__ = [
    "WorkloadGenerator",
    "WorkloadProfile",
    "WorkloadController",
    "load_profile",
    "BUILTIN_PROFILES",
]
