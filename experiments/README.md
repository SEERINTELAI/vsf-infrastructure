# VSF Experiment Framework

Run structured optimization experiments with baseline comparison.

## Quick Start

```python
from experiments import ExperimentRunner, ExperimentDefinition

# Load experiment
exp = ExperimentDefinition.from_yaml("experiments/energy-optimization.yaml")

# Run experiment
runner = ExperimentRunner(exp)
result = await runner.run()

# Compare results
from experiments import ResultComparator

baseline = result.phase_results[0].metrics
optimized = result.phase_results[1].metrics

comparator = ResultComparator(baseline, optimized)
comparison = comparator.compare_all(exp.metrics)

for r in comparison:
    print(r.summary)
```

## Experiment Definition

```yaml
name: energy-optimization-test
description: Test CPU governor optimization

phases:
  - name: baseline
    duration_seconds: 300
    workload: steady-state
    warmup_seconds: 30
    # No optimization - baseline

  - name: powersave
    duration_seconds: 300
    workload: steady-state
    warmup_seconds: 30
    optimization:
      cpu_governor: powersave

metrics:
  - power_watts
  - energy_joules
  - cpu_percent

repetitions: 3
output_dir: /tmp/experiments
```

## Phases

Each phase has:
- **name**: Unique identifier
- **duration_seconds**: How long to run (10-3600s)
- **workload**: Workload profile to use
- **warmup_seconds**: Warmup before collecting metrics
- **optimization**: Optional optimization settings

## Optimizations

```yaml
optimization:
  cpu_governor: powersave  # performance, powersave, ondemand
  gpu_power_limit: 200      # Watts
  io_scheduler: deadline    # deadline, cfq, noop
```

## Metrics

Available metrics:
- `power_watts` - Total system power
- `energy_joules` - Cumulative energy
- `cpu_percent` - CPU utilization
- `memory_percent` - Memory utilization
- `gpu_power` - GPU power consumption
- `gpu_temp` - GPU temperature
- `io_read_bytes` - Disk read rate
- `io_write_bytes` - Disk write rate

## Result Comparison

```python
comparator = ResultComparator(baseline_metrics, optimized_metrics)

# Compare single metric
result = comparator.compare("power_watts")
print(f"Power: {result.percent_improvement:.1f}% improvement")

# Compare all metrics
results = comparator.compare_all(["power_watts", "energy_joules"])
summary = comparator.generate_summary(results)
print(f"Overall power improvement: {summary['power_improvement_percent']}%")
```

## Components

### ExperimentDefinition

Pydantic model for experiment configuration.

```python
exp = ExperimentDefinition(
    name="test",
    phases=[Phase(name="baseline", duration_seconds=60)],
    metrics=["power_watts"]
)
```

### ExperimentRunner

Executes experiments and collects metrics.

- `run(repetition)` - Run single experiment
- `run_all_repetitions()` - Run all configured repetitions
- `cancel()` - Cancel running experiment

### MetricsCollector

Collects metrics from Prometheus and probes.

```python
collector = MetricsCollector(
    prometheus_url="http://prometheus:9090",
    k8s_probe_url="http://k8s-probe:8080"
)
metrics = await collector.collect(["power_watts", "cpu_percent"])
```

### ResultComparator

Statistical comparison of baseline vs optimized.

```python
comparator = ResultComparator(baseline, optimized)
result = comparator.compare("power_watts")
print(f"Improvement: {result.percent_improvement}%")
```

## Files

- `__init__.py` - Package exports
- `definition.py` - Experiment/Phase Pydantic models
- `runner.py` - Experiment execution
- `metrics.py` - Metrics collection
- `comparison.py` - Statistical comparison
- `README.md` - This file
