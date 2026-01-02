"""
Statistical Analysis

Provides statistical analysis functions for experiment results.
"""

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceInterval:
    """Confidence interval result."""
    mean: float
    lower: float
    upper: float
    confidence_level: float = 0.95
    sample_size: int = 0
    
    @property
    def margin(self) -> float:
        return (self.upper - self.lower) / 2
    
    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper


@dataclass
class DescriptiveStats:
    """Descriptive statistics for a sample."""
    count: int
    mean: float
    median: float
    std: float
    min: float
    max: float
    variance: float
    
    @classmethod
    def from_samples(cls, samples: list[float]) -> "DescriptiveStats":
        if not samples:
            return cls(0, 0, 0, 0, 0, 0, 0)
        
        if len(samples) == 1:
            return cls(1, samples[0], samples[0], 0, samples[0], samples[0], 0)
        
        return cls(
            count=len(samples),
            mean=statistics.mean(samples),
            median=statistics.median(samples),
            std=statistics.stdev(samples),
            min=min(samples),
            max=max(samples),
            variance=statistics.variance(samples)
        )


class StatisticalAnalyzer:
    """
    Performs statistical analysis on experiment data.
    
    Usage:
        analyzer = StatisticalAnalyzer()
        stats = analyzer.describe(power_samples)
        ci = analyzer.confidence_interval(power_samples)
    """
    
    # Z-scores for common confidence levels
    Z_SCORES = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576
    }
    
    MIN_SAMPLES = 3
    
    def describe(self, samples: list[float]) -> DescriptiveStats:
        """Calculate descriptive statistics."""
        return DescriptiveStats.from_samples(samples)
    
    def confidence_interval(
        self,
        samples: list[float],
        confidence: float = 0.95
    ) -> ConfidenceInterval:
        """
        Calculate confidence interval.
        
        Args:
            samples: List of sample values
            confidence: Confidence level (0.90, 0.95, or 0.99)
            
        Returns:
            ConfidenceInterval
        """
        if len(samples) < self.MIN_SAMPLES:
            raise ValueError(f"Need at least {self.MIN_SAMPLES} samples for CI")
        
        z = self.Z_SCORES.get(confidence, 1.96)
        mean = statistics.mean(samples)
        std = statistics.stdev(samples)
        n = len(samples)
        
        margin = z * (std / math.sqrt(n))
        
        return ConfidenceInterval(
            mean=mean,
            lower=mean - margin,
            upper=mean + margin,
            confidence_level=confidence,
            sample_size=n
        )
    
    def percent_improvement(
        self,
        baseline: list[float],
        optimized: list[float]
    ) -> tuple[float, ConfidenceInterval | None]:
        """
        Calculate percent improvement with CI.
        
        Args:
            baseline: Baseline samples
            optimized: Optimized samples
            
        Returns:
            (improvement_percent, confidence_interval)
        """
        if not baseline or not optimized:
            return 0.0, None
        
        baseline_mean = statistics.mean(baseline)
        optimized_mean = statistics.mean(optimized)
        
        if baseline_mean == 0:
            return 0.0, None
        
        improvement = (baseline_mean - optimized_mean) / baseline_mean * 100
        
        # Calculate CI for improvement using paired differences
        if len(baseline) == len(optimized) and len(baseline) >= self.MIN_SAMPLES:
            differences = [
                (b - o) / baseline_mean * 100
                for b, o in zip(baseline, optimized)
            ]
            ci = self.confidence_interval(differences)
        else:
            ci = None
        
        return improvement, ci
    
    def aggregate_results(
        self,
        results: list[dict[str, float]],
        metric: str,
        weights: list[float] | None = None
    ) -> DescriptiveStats:
        """
        Aggregate results across multiple experiments.
        
        Args:
            results: List of experiment results
            metric: Metric to aggregate
            weights: Optional weights for weighted average
            
        Returns:
            Aggregated DescriptiveStats
        """
        values = [r[metric] for r in results if metric in r and r[metric] is not None]
        
        if not values:
            return DescriptiveStats(0, 0, 0, 0, 0, 0, 0)
        
        if weights and len(weights) == len(values):
            # Weighted statistics
            total_weight = sum(weights)
            weighted_mean = sum(v * w for v, w in zip(values, weights)) / total_weight
            
            # Weighted variance
            weighted_var = sum(
                w * (v - weighted_mean) ** 2
                for v, w in zip(values, weights)
            ) / total_weight
            
            return DescriptiveStats(
                count=len(values),
                mean=weighted_mean,
                median=statistics.median(values),
                std=math.sqrt(weighted_var),
                min=min(values),
                max=max(values),
                variance=weighted_var
            )
        
        return DescriptiveStats.from_samples(values)
    
    def effect_size_cohens_d(
        self,
        baseline: list[float],
        optimized: list[float]
    ) -> float:
        """
        Calculate Cohen's d effect size.
        
        Args:
            baseline: Baseline samples
            optimized: Optimized samples
            
        Returns:
            Cohen's d value
        """
        if len(baseline) < 2 or len(optimized) < 2:
            return 0.0
        
        mean_diff = statistics.mean(baseline) - statistics.mean(optimized)
        
        # Pooled standard deviation
        n1, n2 = len(baseline), len(optimized)
        var1 = statistics.variance(baseline)
        var2 = statistics.variance(optimized)
        
        pooled_std = math.sqrt(
            ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
        )
        
        if pooled_std == 0:
            return 0.0
        
        return mean_diff / pooled_std
    
    @staticmethod
    def interpret_effect_size(d: float) -> str:
        """Interpret Cohen's d effect size."""
        d = abs(d)
        if d < 0.2:
            return "negligible"
        elif d < 0.5:
            return "small"
        elif d < 0.8:
            return "medium"
        else:
            return "large"
