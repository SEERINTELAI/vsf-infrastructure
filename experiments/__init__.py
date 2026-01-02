"""
VSF Experiment Framework

Run structured optimization experiments with baseline comparison.
"""

__version__ = "1.0.0"

from .runner import ExperimentRunner
from .definition import ExperimentDefinition, Phase
from .metrics import MetricsCollector
from .comparison import ResultComparator

__all__ = [
    "ExperimentRunner",
    "ExperimentDefinition",
    "Phase",
    "MetricsCollector",
    "ResultComparator",
]
