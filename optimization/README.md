# VSF Optimization Framework

Multi-probe coordination and optimization for the Virtual Server Farm.

## Overview

The optimization framework provides:
- **ProbeRouter**: Routes MCP commands to 23 probes
- **MetricsAggregator**: Collects and aggregates cluster metrics
- **OptimizationController**: Makes and executes optimization decisions
- **TestHarness**: Validates closed-loop optimization

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OptimizationController                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Policies:                                                    │   │
│  │  • Consolidation (reduce active nodes)                      │   │
│  │  • Power Save (set powersave governors)                     │   │
│  │  • Performance (set performance governors)                  │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    MetricsAggregator                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Collects: CPU, Memory, Power, Pod counts, Node states      │   │
│  │ Caches: 30-second TTL                                        │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                        ProbeRouter                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Routes to:                                                   │   │
│  │  • 1 K8s Probe (cluster-level)                              │   │
│  │  • 21 VM System Probes (per-VM)                             │   │
│  │  • 1 Host System Probe (Bizon1)                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### ProbeRouter (`router.py`)

Routes MCP tool calls to the appropriate probe.

```python
from optimization.router import ProbeRouter, ProbeType

router = ProbeRouter()

# Register probes
router.register_probe(
    probe_id="k8s-probe",
    probe_type=ProbeType.K8S,
    endpoint="http://k8s-probe:8080/mcp",
    hostname="vsf-cluster"
)

# Route a tool call
result = await router.call_tool(
    target="vsf-worker-1",
    tool_name="system_info",
    params={}
)

# Broadcast to all probes of a type
results = await router.broadcast(
    tool_name="get_cpu_governor",
    params={},
    probe_type=ProbeType.VM_SYSTEM
)
```

### MetricsAggregator (`aggregator.py`)

Collects metrics from all probes and provides a unified view.

```python
from optimization.aggregator import MetricsAggregator

aggregator = MetricsAggregator(router)

# Get all metrics
metrics = await aggregator.collect_all()
print(f"CPU avg: {metrics.avg_cpu_percent}%")
print(f"Power: {metrics.total_power_watts}W")

# Get summary
summary = await aggregator.get_summary()
print(summary)
```

### OptimizationController (`controller.py`)

Makes optimization decisions based on policies.

```python
from optimization.controller import (
    OptimizationController,
    Policy,
    PolicyType
)

controller = OptimizationController(router, aggregator)

# Add a consolidation policy
controller.add_policy(Policy(
    name="consolidate_off_peak",
    policy_type=PolicyType.CONSOLIDATE,
    conditions={"min_nodes": 10},
    parameters={"target_nodes": 5, "dry_run": False}
))

# Run optimization cycle
cycle = await controller.run_optimization_cycle(dry_run=True)
print(controller.get_cycle_summary(cycle))
```

### TestHarness (`test_harness.py`)

Validates closed-loop optimization.

```python
from optimization.test_harness import (
    ClosedLoopTestHarness,
    TestScenario
)

harness = ClosedLoopTestHarness(router, aggregator, controller)

# Run standard tests
scenarios = harness.get_standard_scenarios()
results = await harness.run_all_scenarios(scenarios)

print(f"Passed: {results['passed']}/{results['total']}")
```

## Policy Types

| Type | Description | Actions |
|------|-------------|---------|
| `CONSOLIDATE` | Reduce active nodes | `consolidate_workloads`, `drain_node` |
| `SCALE_DOWN` | Scale down resources | `drain_node`, `cordon_node` |
| `POWER_SAVE` | Reduce power consumption | `set_governor` (powersave) |
| `PERFORMANCE` | Maximize performance | `set_governor` (performance) |

## Configuration

Probe configuration can be loaded from a file:

```yaml
# probes.yml
probes:
  - id: k8s-probe
    type: k8s
    endpoint: http://k8s-probe:8080/mcp
    hostname: vsf-cluster
    
  - id: vsf-cp-1
    type: vm_system
    endpoint: http://vsf-cp-1:8765/mcp
    hostname: vsf-cp-1
    
  # ... more probes
```

```python
from optimization.router import create_router_from_config
from pathlib import Path

router = await create_router_from_config(Path("probes.yml"))
```

## Testing

```bash
# Run unit tests
pytest tests/test_agentone_integration.py -v

# Run with specific markers
pytest tests/test_agentone_integration.py -v -m integration
```

## Closed-Loop Test Flow

1. **Capture Initial State**: Collect metrics from all probes
2. **Evaluate Policies**: Determine needed optimizations
3. **Plan Actions**: Create ordered action list
4. **Execute Actions**: Run (or dry-run) each action
5. **Capture Final State**: Collect post-optimization metrics
6. **Validate Results**: Check expected outcomes

## Safety Features

- **Dry Run Mode**: Plan without executing (default)
- **Action Ordering**: Priority-based execution
- **Rollback Support**: Action history for reverting
- **Health Monitoring**: Automatic probe health tracking
- **Retries**: Configurable retry on failure
