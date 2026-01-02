# VSF Hardware Safety Module

⚠️ **PRIORITY 0 - NON-NEGOTIABLE** ⚠️

This module provides hardware safety protection for VSF workload generation.
**All workloads MUST use this module.**

## Quick Start

```python
from safety import HardwareSafetyMonitor, SafeWorkloadContext

# Option 1: Manual control
async def run_workload():
    monitor = HardwareSafetyMonitor()
    
    # Pre-flight check (REQUIRED)
    result = await monitor.pre_flight_check()
    if not result.safe:
        print(f"Cannot start: {result.reason}")
        return
    
    # Start monitoring
    await monitor.start_runtime_monitoring()
    
    try:
        # ... run workload ...
        pass
    finally:
        await monitor.stop_runtime_monitoring()

# Option 2: Context manager (RECOMMENDED)
async def run_workload_safe():
    async with SafeWorkloadContext() as ctx:
        if not ctx.safe:
            return  # Pre-flight failed
        
        # ... run workload ...
        pass  # Monitoring runs automatically
```

## Safety Constraints

### Temperature Limits

| Component | Warning | **HARD STOP** |
|-----------|---------|---------------|
| GPU | 80°C | 85°C |
| CPU | 90°C | 95°C |

### Power Limits

| Metric | Warning | **HARD STOP** |
|--------|---------|---------------|
| Total System | 2000W | 2200W |
| Per GPU | 250W | 300W |

### Resource Limits

| Resource | Maximum |
|----------|---------|
| CPU | 80% |
| Memory | 85% |
| GPU Memory | 90% |
| Workload Intensity | 80% |

## Components

### `HardwareSafetyMonitor`

Main safety monitor class.

**Methods:**
- `pre_flight_check()` - Check before starting workloads
- `start_runtime_monitoring()` - Start 10-second monitoring loop
- `stop_runtime_monitoring()` - Stop monitoring
- `emergency_stop()` - Kill all workloads immediately
- `collect_metrics()` - Get current hardware metrics

### `SafetyConstraints`

Immutable constraint configuration.

```python
from safety.constraints import DEFAULT_CONSTRAINTS, BIZON1_CONSTRAINTS

# Use Bizon1-specific (more conservative)
monitor = HardwareSafetyMonitor(constraints=BIZON1_CONSTRAINTS)
```

### `SafeWorkloadContext`

Context manager for safe workload execution.

```python
async with SafeWorkloadContext() as ctx:
    if ctx.safe:
        # Pre-flight passed, monitoring active
        ...
# Monitoring automatically stopped
```

## Callbacks

Register callbacks for warning/critical conditions:

```python
def on_warning(result: SafetyResult):
    print(f"Warning: {result.reason}")
    # Reduce workload intensity

def on_critical(result: SafetyResult):
    print(f"CRITICAL: {result.reason}")
    # Workload will be terminated

monitor = HardwareSafetyMonitor()
monitor.on_warning(on_warning)
monitor.on_critical(on_critical)
```

## Emergency Stop

The emergency stop procedure:
1. Force-kills all pods with `vsf-workload=true` label
2. Scales all workload deployments to 0
3. Logs critical message

```python
await monitor.emergency_stop()
```

## Actions

| Action | Trigger | Response |
|--------|---------|----------|
| `PROCEED` | All checks pass | Continue |
| `WAIT_COOLDOWN` | GPU temp 80-84°C | Wait 60s |
| `REDUCE_INTENSITY` | Power warning, resource high | Cut to 50% |
| `ABORT` | Any critical threshold | Emergency stop |

## Integration with Workload Generator

```python
from safety import SafeWorkloadContext
from workloads import WorkloadGenerator

async def generate_safe_workload(profile):
    async with SafeWorkloadContext(
        on_warning=lambda r: generator.reduce_intensity(0.5)
    ) as ctx:
        if not ctx.safe:
            raise RuntimeError("Safety check failed")
        
        generator = WorkloadGenerator()
        await generator.deploy(profile)
```

## Files

- `__init__.py` - Package exports
- `constraints.py` - Safety limits configuration
- `monitor.py` - Main safety monitor implementation
- `README.md` - This file
