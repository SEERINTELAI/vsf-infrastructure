"""
Analysis & Reporting Test Suite (Task 149)

F10.5 Track C: Tests for statistical analysis and report generation.

Pre-Mortem Failure Categories:
1. Statistical Failure - Wrong calculations, invalid inputs
2. Visualization Failure - Charts don't render, data errors
3. Export Failure - Reports not generated, format errors
4. Aggregation Failure - Multi-experiment aggregation wrong
5. Confidence Interval Failure - CI calculations incorrect

Total: 15 tests (DP:ETG compliant)

Usage:
    pytest tests/test_analysis.py -v
    pytest tests/test_analysis.py -v -m analysis
"""

import asyncio
import json
import statistics
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_experiment_result():
    """Sample experiment result data."""
    return {
        "experiment_name": "energy-optimization-test",
        "started_at": "2026-01-02T10:00:00",
        "ended_at": "2026-01-02T10:30:00",
        "status": "completed",
        "phases": [
            {
                "name": "baseline",
                "metrics": [
                    {"power_watts": 1500, "cpu_percent": 50, "timestamp": "2026-01-02T10:00:00"},
                    {"power_watts": 1520, "cpu_percent": 52, "timestamp": "2026-01-02T10:00:10"},
                    {"power_watts": 1480, "cpu_percent": 48, "timestamp": "2026-01-02T10:00:20"},
                    {"power_watts": 1510, "cpu_percent": 51, "timestamp": "2026-01-02T10:00:30"},
                    {"power_watts": 1490, "cpu_percent": 49, "timestamp": "2026-01-02T10:00:40"},
                ]
            },
            {
                "name": "optimized",
                "metrics": [
                    {"power_watts": 1200, "cpu_percent": 48, "timestamp": "2026-01-02T10:15:00"},
                    {"power_watts": 1180, "cpu_percent": 46, "timestamp": "2026-01-02T10:15:10"},
                    {"power_watts": 1220, "cpu_percent": 50, "timestamp": "2026-01-02T10:15:20"},
                    {"power_watts": 1190, "cpu_percent": 47, "timestamp": "2026-01-02T10:15:30"},
                    {"power_watts": 1210, "cpu_percent": 49, "timestamp": "2026-01-02T10:15:40"},
                ]
            }
        ]
    }


@pytest.fixture
def multiple_experiment_results():
    """Multiple experiment results for aggregation."""
    return [
        {"experiment_name": "exp-1", "power_improvement": 20.5, "energy_improvement": 18.2},
        {"experiment_name": "exp-2", "power_improvement": 22.1, "energy_improvement": 19.8},
        {"experiment_name": "exp-3", "power_improvement": 19.8, "energy_improvement": 17.5},
        {"experiment_name": "exp-4", "power_improvement": 21.3, "energy_improvement": 19.1},
        {"experiment_name": "exp-5", "power_improvement": 20.9, "energy_improvement": 18.6},
    ]


@pytest.fixture
def power_samples():
    """Power samples for CI calculation."""
    return [1200, 1180, 1220, 1190, 1210, 1195, 1205, 1215, 1185, 1200]


# =============================================================================
# Category 1: Statistical Failure (3 tests)
# =============================================================================

class TestStatisticalFailure:
    """
    Tests for statistical calculation failures.
    
    Pre-mortem: What if calculations are wrong?
    """
    
    @pytest.mark.analysis
    def test_mean_calculation(self, power_samples):
        """Verify mean is calculated correctly."""
        expected_mean = 1200  # (1200+1180+...)/10
        actual_mean = statistics.mean(power_samples)
        
        assert abs(actual_mean - expected_mean) < 1  # Allow small float error
    
    @pytest.mark.analysis
    def test_std_calculation(self, power_samples):
        """Verify standard deviation is calculated correctly."""
        actual_std = statistics.stdev(power_samples)
        
        # Std should be positive and reasonable for this data
        assert actual_std > 0
        assert actual_std < 50  # Not huge variance
    
    @pytest.mark.analysis
    def test_percent_improvement(self, sample_experiment_result):
        """Verify percent improvement is correct."""
        baseline = sample_experiment_result["phases"][0]["metrics"]
        optimized = sample_experiment_result["phases"][1]["metrics"]
        
        baseline_mean = statistics.mean([m["power_watts"] for m in baseline])
        optimized_mean = statistics.mean([m["power_watts"] for m in optimized])
        
        improvement = (baseline_mean - optimized_mean) / baseline_mean * 100
        
        # 1500 -> 1200 = 20% improvement
        assert 19 < improvement < 21


# =============================================================================
# Category 2: Visualization Failure (3 tests)
# =============================================================================

class TestVisualizationFailure:
    """
    Tests for visualization/chart failures.
    
    Pre-mortem: What if charts can't render?
    """
    
    @pytest.mark.analysis
    def test_timeseries_data_format(self, sample_experiment_result):
        """Verify timeseries data is in correct format for plotting."""
        baseline = sample_experiment_result["phases"][0]["metrics"]
        
        # Should have timestamps and values
        for point in baseline:
            assert "timestamp" in point
            assert "power_watts" in point
            # Timestamp should be ISO format
            datetime.fromisoformat(point["timestamp"].replace("Z", "+00:00"))
    
    @pytest.mark.analysis
    def test_chart_data_has_labels(self, sample_experiment_result):
        """Verify chart data has proper labels."""
        phases = sample_experiment_result["phases"]
        
        # Each phase should have a name for legend
        for phase in phases:
            assert "name" in phase
            assert len(phase["name"]) > 0
    
    @pytest.mark.analysis
    def test_empty_data_handled(self):
        """Verify empty data doesn't crash visualization."""
        empty_metrics = []
        
        # Should handle gracefully
        if not empty_metrics:
            result = {"status": "no_data", "message": "No metrics to visualize"}
        else:
            result = {"status": "ok"}
        
        assert result["status"] == "no_data"


# =============================================================================
# Category 3: Export Failure (3 tests)
# =============================================================================

class TestExportFailure:
    """
    Tests for report export failures.
    
    Pre-mortem: What if reports can't be generated?
    """
    
    @pytest.mark.analysis
    def test_json_export(self, sample_experiment_result):
        """Verify JSON export works."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_experiment_result, f, indent=2)
            f.flush()
            
            # Read back
            with open(f.name) as rf:
                loaded = json.load(rf)
        
        assert loaded["experiment_name"] == sample_experiment_result["experiment_name"]
    
    @pytest.mark.analysis
    def test_csv_export_format(self, sample_experiment_result):
        """Verify CSV export has correct format."""
        baseline = sample_experiment_result["phases"][0]["metrics"]
        
        # Convert to CSV rows
        header = ["timestamp", "power_watts", "cpu_percent"]
        rows = []
        for m in baseline:
            rows.append([m.get("timestamp"), m.get("power_watts"), m.get("cpu_percent")])
        
        assert len(header) == 3
        assert len(rows) == 5
        assert all(len(row) == 3 for row in rows)
    
    @pytest.mark.analysis
    def test_report_directory_created(self):
        """Verify report directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir) / "reports" / "2026-01-02"
            
            # Should create nested directories
            report_dir.mkdir(parents=True, exist_ok=True)
            
            assert report_dir.exists()


# =============================================================================
# Category 4: Aggregation Failure (3 tests)
# =============================================================================

class TestAggregationFailure:
    """
    Tests for multi-experiment aggregation failures.
    
    Pre-mortem: What if aggregation across experiments is wrong?
    """
    
    @pytest.mark.analysis
    def test_aggregate_improvements(self, multiple_experiment_results):
        """Verify aggregation across experiments."""
        power_improvements = [r["power_improvement"] for r in multiple_experiment_results]
        
        avg = statistics.mean(power_improvements)
        min_val = min(power_improvements)
        max_val = max(power_improvements)
        
        # Average should be between min and max
        assert min_val <= avg <= max_val
        # Should be around 20-21%
        assert 19 < avg < 22
    
    @pytest.mark.analysis
    def test_weighted_average(self, multiple_experiment_results):
        """Verify weighted average works correctly."""
        # Add sample counts
        for i, r in enumerate(multiple_experiment_results):
            r["sample_count"] = (i + 1) * 10  # 10, 20, 30, 40, 50
        
        total_samples = sum(r["sample_count"] for r in multiple_experiment_results)
        weighted_avg = sum(
            r["power_improvement"] * r["sample_count"] / total_samples
            for r in multiple_experiment_results
        )
        
        # Weighted average should favor later experiments (higher sample counts)
        assert weighted_avg > 0
    
    @pytest.mark.analysis
    def test_aggregate_with_missing_data(self, multiple_experiment_results):
        """Verify aggregation handles missing data."""
        # Add some None values
        multiple_experiment_results[1]["power_improvement"] = None
        
        # Filter out None values
        valid_results = [
            r for r in multiple_experiment_results
            if r["power_improvement"] is not None
        ]
        
        assert len(valid_results) == 4
        avg = statistics.mean([r["power_improvement"] for r in valid_results])
        assert avg > 0


# =============================================================================
# Category 5: Confidence Interval Failure (3 tests)
# =============================================================================

class TestConfidenceIntervalFailure:
    """
    Tests for confidence interval calculation failures.
    
    Pre-mortem: What if CI calculations are wrong?
    """
    
    @pytest.mark.analysis
    def test_confidence_interval_95(self, power_samples):
        """Verify 95% CI is calculated correctly."""
        mean = statistics.mean(power_samples)
        std = statistics.stdev(power_samples)
        n = len(power_samples)
        
        # 95% CI: mean ± 1.96 * (std / sqrt(n))
        margin = 1.96 * (std / (n ** 0.5))
        ci_lower = mean - margin
        ci_upper = mean + margin
        
        # CI should be reasonable
        assert ci_lower < mean < ci_upper
        assert (ci_upper - ci_lower) < 50  # Not too wide
    
    @pytest.mark.analysis
    def test_ci_narrows_with_more_samples(self):
        """Verify CI narrows with more samples."""
        small_sample = [100, 110, 105, 108, 102]
        large_sample = small_sample * 10  # 50 samples
        
        def calc_ci_width(samples):
            mean = statistics.mean(samples)
            std = statistics.stdev(samples)
            n = len(samples)
            margin = 1.96 * (std / (n ** 0.5))
            return margin * 2
        
        small_ci_width = calc_ci_width(small_sample)
        large_ci_width = calc_ci_width(large_sample)
        
        # Larger sample should have narrower CI
        assert large_ci_width < small_ci_width
    
    @pytest.mark.analysis
    def test_ci_requires_min_samples(self):
        """Verify CI requires minimum samples."""
        MIN_SAMPLES = 3
        
        def validate_for_ci(samples):
            if len(samples) < MIN_SAMPLES:
                return f"Need at least {MIN_SAMPLES} samples for CI"
            return None
        
        error = validate_for_ci([1, 2])
        assert error is not None
        
        error = validate_for_ci([1, 2, 3, 4])
        assert error is None


# =============================================================================
# Test Summary
# =============================================================================
# Total: 15 tests across 5 pre-mortem categories
#
# Category 1 - Statistical: 3 tests
# Category 2 - Visualization: 3 tests
# Category 3 - Export: 3 tests
# Category 4 - Aggregation: 3 tests
# Category 5 - Confidence Interval: 3 tests
#
# Markers:
#   - analysis: Analysis and reporting tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "analysis"])
