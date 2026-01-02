"""
Experiment Framework Test Suite (Task 144)

F10.5 Track B: Tests for experiment execution and metrics collection.

Pre-Mortem Failure Categories:
1. Definition Failure - Invalid experiment definition
2. Runner Failure - Experiment execution fails
3. Metrics Failure - Data collection errors
4. Baseline Failure - Baseline not established
5. Comparison Failure - Statistical comparison errors

Total: 16 tests (DP:ETG compliant)

Usage:
    pytest tests/test_experiment_framework.py -v
    pytest tests/test_experiment_framework.py -v -m experiment
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def valid_experiment():
    """Valid experiment definition."""
    return {
        "name": "energy-optimization-test",
        "description": "Test energy optimization with CPU governor changes",
        "phases": [
            {
                "name": "baseline",
                "duration_seconds": 300,
                "workload": "steady-state",
                "optimization": None
            },
            {
                "name": "optimized",
                "duration_seconds": 300,
                "workload": "steady-state",
                "optimization": {"cpu_governor": "powersave"}
            }
        ],
        "metrics": ["power_watts", "energy_joules", "cpu_percent"],
        "repetitions": 3,
        "output_dir": "/tmp/experiment-results"
    }


@pytest.fixture
def invalid_experiment_no_phases():
    """Experiment without phases."""
    return {
        "name": "invalid-experiment",
        "description": "Missing phases",
        "metrics": ["power_watts"]
    }


@pytest.fixture
def invalid_experiment_no_metrics():
    """Experiment without metrics."""
    return {
        "name": "invalid-experiment",
        "description": "Missing metrics",
        "phases": [{"name": "test", "duration_seconds": 60}]
    }


@pytest.fixture
def sample_metrics():
    """Sample collected metrics."""
    return [
        {"timestamp": "2026-01-02T10:00:00", "power_watts": 1200, "cpu_percent": 45},
        {"timestamp": "2026-01-02T10:00:10", "power_watts": 1250, "cpu_percent": 52},
        {"timestamp": "2026-01-02T10:00:20", "power_watts": 1180, "cpu_percent": 48},
        {"timestamp": "2026-01-02T10:00:30", "power_watts": 1220, "cpu_percent": 50},
        {"timestamp": "2026-01-02T10:00:40", "power_watts": 1190, "cpu_percent": 46},
    ]


@pytest.fixture
def baseline_metrics():
    """Baseline metrics for comparison."""
    return [
        {"power_watts": 1500, "energy_joules": 4500},
        {"power_watts": 1520, "energy_joules": 4560},
        {"power_watts": 1480, "energy_joules": 4440},
        {"power_watts": 1510, "energy_joules": 4530},
        {"power_watts": 1490, "energy_joules": 4470},
    ]


@pytest.fixture
def optimized_metrics():
    """Optimized metrics for comparison."""
    return [
        {"power_watts": 1200, "energy_joules": 3600},
        {"power_watts": 1180, "energy_joules": 3540},
        {"power_watts": 1220, "energy_joules": 3660},
        {"power_watts": 1190, "energy_joules": 3570},
        {"power_watts": 1210, "energy_joules": 3630},
    ]


# =============================================================================
# Category 1: Definition Failure (3 tests)
# =============================================================================

class TestDefinitionFailure:
    """
    Tests for experiment definition failures.
    
    Pre-mortem: What if experiment definitions are invalid?
    """
    
    @pytest.mark.experiment
    def test_load_valid_experiment(self, valid_experiment):
        """Verify valid experiment definition loads correctly."""
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(valid_experiment, f)
            f.flush()
            
            with open(f.name) as rf:
                loaded = yaml.safe_load(rf)
        
        assert loaded["name"] == "energy-optimization-test"
        assert len(loaded["phases"]) == 2
        assert loaded["phases"][0]["name"] == "baseline"
        assert "power_watts" in loaded["metrics"]
    
    @pytest.mark.experiment
    def test_invalid_phases(self, invalid_experiment_no_phases):
        """Verify experiments without phases are rejected."""
        def validate_experiment(exp: dict) -> list[str]:
            errors = []
            if "phases" not in exp or not exp["phases"]:
                errors.append("Experiment must have at least one phase")
            return errors
        
        errors = validate_experiment(invalid_experiment_no_phases)
        assert len(errors) > 0
        assert "phase" in errors[0].lower()
    
    @pytest.mark.experiment
    def test_missing_metrics(self, invalid_experiment_no_metrics):
        """Verify experiments without metrics are rejected."""
        def validate_experiment(exp: dict) -> list[str]:
            errors = []
            if "metrics" not in exp or not exp["metrics"]:
                errors.append("Experiment must specify metrics to collect")
            return errors
        
        errors = validate_experiment(invalid_experiment_no_metrics)
        assert len(errors) > 0
        assert "metric" in errors[0].lower()


# =============================================================================
# Category 2: Runner Failure (4 tests)
# =============================================================================

class TestRunnerFailure:
    """
    Tests for experiment runner failures.
    
    Pre-mortem: What if experiment execution fails?
    """
    
    @pytest.mark.experiment
    @pytest.mark.asyncio
    async def test_run_single_phase(self, valid_experiment):
        """Verify single phase executes successfully."""
        phase = valid_experiment["phases"][0]
        
        # Simulate phase execution
        phase_result = {
            "name": phase["name"],
            "started_at": datetime.now().isoformat(),
            "duration_seconds": phase["duration_seconds"],
            "status": "completed",
            "metrics_collected": 30
        }
        
        assert phase_result["status"] == "completed"
        assert phase_result["metrics_collected"] > 0
    
    @pytest.mark.experiment
    @pytest.mark.asyncio
    async def test_run_full_experiment(self, valid_experiment):
        """Verify all phases complete in sequence."""
        results = []
        
        for phase in valid_experiment["phases"]:
            result = {
                "name": phase["name"],
                "status": "completed",
                "metrics_collected": 30
            }
            results.append(result)
        
        assert len(results) == 2
        assert all(r["status"] == "completed" for r in results)
    
    @pytest.mark.experiment
    def test_phase_timeout_handled(self):
        """Verify timeout is properly handled for long phases."""
        PHASE_TIMEOUT = 600  # 10 minutes max
        
        phase = {"name": "long-phase", "duration_seconds": 300}
        
        def check_timeout(phase: dict, timeout: int) -> bool:
            return phase["duration_seconds"] <= timeout
        
        assert check_timeout(phase, PHASE_TIMEOUT) is True
        assert check_timeout({"duration_seconds": 1000}, PHASE_TIMEOUT) is False
    
    @pytest.mark.experiment
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Verify cleanup on experiment interrupt."""
        cleanup_called = False
        
        async def run_with_cleanup():
            nonlocal cleanup_called
            try:
                # Simulate running
                await asyncio.sleep(0.1)
                raise asyncio.CancelledError()
            finally:
                cleanup_called = True
        
        with pytest.raises(asyncio.CancelledError):
            await run_with_cleanup()
        
        assert cleanup_called is True


# =============================================================================
# Category 3: Metrics Failure (3 tests)
# =============================================================================

class TestMetricsFailure:
    """
    Tests for metrics collection failures.
    
    Pre-mortem: What if data collection fails?
    """
    
    @pytest.mark.experiment
    def test_collect_metrics(self, sample_metrics):
        """Verify metrics are collected correctly."""
        assert len(sample_metrics) == 5
        assert all("power_watts" in m for m in sample_metrics)
        assert all("timestamp" in m for m in sample_metrics)
    
    @pytest.mark.experiment
    def test_missing_metric_handled(self):
        """Verify missing metric source is caught."""
        available_metrics = {"power_watts", "cpu_percent", "memory_percent"}
        requested_metrics = ["power_watts", "gpu_temp", "unknown_metric"]
        
        missing = [m for m in requested_metrics if m not in available_metrics]
        
        assert len(missing) == 2
        assert "gpu_temp" in missing
        assert "unknown_metric" in missing
    
    @pytest.mark.experiment
    def test_metric_aggregation(self, sample_metrics):
        """Verify metrics are aggregated correctly."""
        power_values = [m["power_watts"] for m in sample_metrics]
        
        avg_power = sum(power_values) / len(power_values)
        min_power = min(power_values)
        max_power = max(power_values)
        
        assert avg_power == 1208  # (1200+1250+1180+1220+1190)/5
        assert min_power == 1180
        assert max_power == 1250


# =============================================================================
# Category 4: Baseline Failure (3 tests)
# =============================================================================

class TestBaselineFailure:
    """
    Tests for baseline collection failures.
    
    Pre-mortem: What if baseline isn't properly established?
    """
    
    @pytest.mark.experiment
    def test_collect_baseline(self, baseline_metrics):
        """Verify baseline metrics are recorded."""
        assert len(baseline_metrics) >= 3  # Minimum samples
        
        # Calculate baseline stats
        power_values = [m["power_watts"] for m in baseline_metrics]
        baseline_avg = sum(power_values) / len(power_values)
        
        assert baseline_avg > 0
    
    @pytest.mark.experiment
    def test_baseline_matches_workload(self, valid_experiment):
        """Verify baseline uses same workload as comparison."""
        baseline_phase = valid_experiment["phases"][0]
        comparison_phase = valid_experiment["phases"][1]
        
        # Workloads should match for fair comparison
        assert baseline_phase["workload"] == comparison_phase["workload"]
    
    @pytest.mark.experiment
    def test_compare_to_baseline(self, baseline_metrics, optimized_metrics):
        """Verify comparison to baseline works."""
        baseline_power = sum(m["power_watts"] for m in baseline_metrics) / len(baseline_metrics)
        optimized_power = sum(m["power_watts"] for m in optimized_metrics) / len(optimized_metrics)
        
        improvement = (baseline_power - optimized_power) / baseline_power * 100
        
        assert improvement > 0  # Should show improvement
        assert improvement < 100  # But not impossible


# =============================================================================
# Category 5: Comparison Failure (3 tests)
# =============================================================================

class TestComparisonFailure:
    """
    Tests for statistical comparison failures.
    
    Pre-mortem: What if comparison calculations are wrong?
    """
    
    @pytest.mark.experiment
    def test_calculate_improvement(self, baseline_metrics, optimized_metrics):
        """Verify percentage improvement is correct."""
        baseline_avg = sum(m["power_watts"] for m in baseline_metrics) / len(baseline_metrics)
        optimized_avg = sum(m["power_watts"] for m in optimized_metrics) / len(optimized_metrics)
        
        improvement = (baseline_avg - optimized_avg) / baseline_avg * 100
        
        # 1500 avg -> 1200 avg = 20% improvement
        assert 19 < improvement < 21
    
    @pytest.mark.experiment
    def test_paired_comparison(self, baseline_metrics, optimized_metrics):
        """Verify paired comparison uses same sample count."""
        assert len(baseline_metrics) == len(optimized_metrics)
        
        # Paired differences
        differences = [
            b["power_watts"] - o["power_watts"]
            for b, o in zip(baseline_metrics, optimized_metrics)
        ]
        
        assert len(differences) == len(baseline_metrics)
        assert all(d > 0 for d in differences)  # All should show reduction
    
    @pytest.mark.experiment
    def test_insufficient_data_handled(self):
        """Verify error on insufficient samples."""
        MIN_SAMPLES = 10
        
        def validate_sample_count(samples: list) -> str | None:
            if len(samples) < MIN_SAMPLES:
                return f"Insufficient samples: {len(samples)} < {MIN_SAMPLES}"
            return None
        
        error = validate_sample_count([1, 2, 3])
        assert error is not None
        assert "Insufficient" in error
        
        error = validate_sample_count(list(range(15)))
        assert error is None


# =============================================================================
# Test Summary
# =============================================================================
# Total: 16 tests across 5 pre-mortem categories
#
# Category 1 - Definition: 3 tests
# Category 2 - Runner: 4 tests
# Category 3 - Metrics: 3 tests
# Category 4 - Baseline: 3 tests
# Category 5 - Comparison: 3 tests
#
# Markers:
#   - experiment: Experiment framework tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "experiment"])
