# VSF Workload Generation

Generates K8s workloads for F10.5 benchmarking and optimization experiments.

## Quick Start

```python
from workloads import WorkloadGenerator, WorkloadController, BUILTIN_PROFILES
from safety import SafeWorkloadContext

async def run_workload():
    # Use safety context (REQUIRED)
    async with SafeWorkloadContext() as ctx:
        if not ctx.safe:
            print("Safety check failed")
            return
        
        # Generate workload
        generator = WorkloadGenerator()
        profile = BUILTIN_PROFILES["steady-state"]
        manifest = generator.generate(profile)
        
        # Deploy
        await generator.apply(manifest)
        
        # Apply intensity pattern
        controller = WorkloadController()
        await controller.apply_pattern(
            profile.name,
            profile.namespace,
            profile.pattern,
            profile.replicas,
            profile.duration_seconds
        )
        
        # Cleanup
        await generator.cleanup()
```

## Built-in Profiles

| Profile | Type | Replicas | Intensity | Duration |
|---------|------|----------|-----------|----------|
| `steady-state` | Deployment | 5 | 0.5 | 600s |
| `bursty` | Deployment | 10 | 0.7 | 300s |
| `diurnal` | Deployment | 8 | 0.6 | 900s |
| `batch-gpu` | Job | 1 (4 parallel) | 0.8 | 600s |
| `mixed` | Deployment | 6 | 0.55 | 450s |

## Custom Profiles

```yaml
# my-profile.yaml
name: custom-workload
type: deployment
namespace: vsf-workloads
replicas: 10
resources:
  requests:
    cpu: "200m"
    memory: "256Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
intensity: 0.6
pattern: bursty
duration_seconds: 600
labels:
  team: "ml"
  experiment: "energy-opt"
```

```python
from workloads import load_profile

profile = load_profile("my-profile.yaml")
```

## Intensity Patterns

| Pattern | Description |
|---------|-------------|
| `steady-state` | Constant intensity |
| `bursty` | Alternates between low and high every 30s |
| `diurnal` | Sinusoidal wave over duration |
| `batch-gpu` | Full intensity for GPU batches |
| `mixed` | Multi-frequency wave |

## Safety Integration

**PRIORITY 0**: All workloads MUST use `SafeWorkloadContext`:

1. Pre-flight check before deployment
2. Runtime monitoring during execution
3. Emergency stop on critical conditions

```python
from safety import SafeWorkloadContext

async with SafeWorkloadContext() as ctx:
    if ctx.safe:
        # Safe to run workload
        ...
```

## Components

### WorkloadGenerator

Generates K8s manifests from profiles.

- `generate_deployment(profile)` - Generate Deployment
- `generate_job(profile)` - Generate Job
- `apply(manifest)` - Apply to cluster
- `delete(manifest)` - Delete from cluster
- `cleanup()` - Delete all deployed resources

### WorkloadController

Controls intensity and applies patterns.

- `scale(deployment, namespace, replicas)` - Scale deployment
- `apply_pattern(...)` - Apply time-based pattern
- `get_intensity(pattern, elapsed, duration)` - Get intensity value

### WorkloadProfile

Pydantic model for profile validation.

- Intensity capped at 0.8 (safety)
- vsf-workload label auto-added
- Resource validation

## Files

- `__init__.py` - Package exports
- `profiles.py` - Profile definitions and built-ins
- `generator.py` - K8s manifest generation
- `controller.py` - Intensity pattern control
- `README.md` - This file
