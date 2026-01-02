"""
VSF Optimization Framework

Multi-probe coordination and optimization for the Virtual Server Farm.

Components:
- ProbeRouter: Routes MCP commands to appropriate probes
- MetricsAggregator: Collects and aggregates metrics from all probes
- OptimizationController: Makes optimization decisions based on policies
- TestHarness: Validates closed-loop optimization
"""

__version__ = "0.1.0"

from .router import ProbeRouter, ProbeInfo
from .aggregator import MetricsAggregator
from .controller import OptimizationController

__all__ = [
    "ProbeRouter",
    "ProbeInfo",
    "MetricsAggregator",
    "OptimizationController",
]
