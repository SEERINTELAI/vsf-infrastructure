"""
Result Comparison

Statistical comparison of experiment results.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of comparing baseline vs optimized."""
    metric: str
    baseline_mean: float
    baseline_std: float
    optimized_mean: float
    optimized_std: float
    absolute_difference: float
    percent_improvement: float
    sample_count: int
    is_significant: bool = True  # Simplified - would use t-test in production
    
    @property
    def summary(self) -> str:
        direction = "↓" if self.percent_improvement > 0 else "↑"
        return f"{self.metric}: {abs(self.percent_improvement):.1f}% {direction}"


class ResultComparator:
    """
    Compares baseline and optimized experiment results.
    
    Usage:
        comparator = ResultComparator(baseline_metrics, optimized_metrics)
        results = comparator.compare_all(["power_watts", "energy_joules"])
    """
    
    MIN_SAMPLES = 10
    
    def __init__(
        self,
        baseline_samples: list[dict[str, Any]],
        optimized_samples: list[dict[str, Any]]
    ):
        self.baseline = baseline_samples
        self.optimized = optimized_samples
    
    def _extract_values(self, samples: list[dict], metric: str) -> list[float]:
        """Extract metric values from samples."""
        return [s[metric] for s in samples if metric in s and s[metric] is not None]
    
    def _calculate_stats(self, values: list[float]) -> tuple[float, float]:
        """Calculate mean and std of values."""
        if len(values) < 2:
            return values[0] if values else 0, 0
        
        return statistics.mean(values), statistics.stdev(values)
    
    def compare(self, metric: str) -> ComparisonResult:
        """
        Compare a single metric between baseline and optimized.
        
        Args:
            metric: Metric name
            
        Returns:
            ComparisonResult
        """
        baseline_values = self._extract_values(self.baseline, metric)
        optimized_values = self._extract_values(self.optimized, metric)
        
        if len(baseline_values) < 2 or len(optimized_values) < 2:
            logger.warning(f"Insufficient samples for {metric}")
        
        baseline_mean, baseline_std = self._calculate_stats(baseline_values)
        optimized_mean, optimized_std = self._calculate_stats(optimized_values)
        
        absolute_diff = baseline_mean - optimized_mean
        percent_improvement = (absolute_diff / baseline_mean * 100) if baseline_mean != 0 else 0
        
        return ComparisonResult(
            metric=metric,
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            optimized_mean=optimized_mean,
            optimized_std=optimized_std,
            absolute_difference=absolute_diff,
            percent_improvement=percent_improvement,
            sample_count=min(len(baseline_values), len(optimized_values))
        )
    
    def compare_all(self, metrics: list[str]) -> list[ComparisonResult]:
        """
        Compare all specified metrics.
        
        Args:
            metrics: List of metric names
            
        Returns:
            List of ComparisonResults
        """
        return [self.compare(m) for m in metrics]
    
    def generate_summary(self, results: list[ComparisonResult]) -> dict[str, Any]:
        """Generate summary of comparison results."""
        power_metrics = [r for r in results if "power" in r.metric or "energy" in r.metric]
        
        total_power_improvement = 0
        if power_metrics:
            total_power_improvement = statistics.mean([r.percent_improvement for r in power_metrics])
        
        return {
            "total_metrics_compared": len(results),
            "power_improvement_percent": round(total_power_improvement, 2),
            "metrics_improved": sum(1 for r in results if r.percent_improvement > 0),
            "metrics_regressed": sum(1 for r in results if r.percent_improvement < 0),
            "details": [
                {
                    "metric": r.metric,
                    "baseline": round(r.baseline_mean, 2),
                    "optimized": round(r.optimized_mean, 2),
                    "improvement_percent": round(r.percent_improvement, 2)
                }
                for r in results
            ]
        }
    
    def validate_sample_count(self) -> str | None:
        """Validate sufficient samples exist."""
        baseline_count = len(self.baseline)
        optimized_count = len(self.optimized)
        
        if baseline_count < self.MIN_SAMPLES:
            return f"Insufficient baseline samples: {baseline_count} < {self.MIN_SAMPLES}"
        
        if optimized_count < self.MIN_SAMPLES:
            return f"Insufficient optimized samples: {optimized_count} < {self.MIN_SAMPLES}"
        
        if baseline_count != optimized_count:
            logger.warning(f"Sample count mismatch: {baseline_count} vs {optimized_count}")
        
        return None
