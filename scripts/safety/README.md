# Safety Scripts for F10.2

Pre-flight checks, rollback scripts, and validation tests for high-risk F10.2 tasks.

## Overview

These scripts were created based on adversarial analysis by a swarm of 5 agents that critiqued the original mitigation strategies for Tasks 111 (GPU Operator) and 115 (Kepler).

## Scripts

### Pre-Flight Checks (Run BEFORE deployment)

| Script | Task | Purpose |
|--------|------|---------|
| `pre-flight-gpu.sh` | 111 | Comprehensive GPU compatibility check |
| `pre-flight-power.sh` | 115 | Multi-source RAPL validation |

### Rollback Scripts (Run IF deployment fails)

| Script | Task | Purpose |
|--------|------|---------|
| `gpu-operator-rollback.sh` | 111 | Safely revert GPU Operator deployment |

### Validation Tests (Run AFTER deployment)

| Script | Task | Purpose |
|--------|------|---------|
| `kepler-validation-test.py` | 115 | Cross-validate Kepler vs Scaphandre metrics |

## Usage

### Before Task 111 (GPU Operator)

```bash
# 1. Run pre-flight GPU checks on all GPU workers
./pre-flight-gpu.sh --all

# 2. If checks pass, proceed with deployment
# 3. If deployment fails, run rollback
./gpu-operator-rollback.sh
```

### Before Task 115 (Kepler)

```bash
# 1. Run pre-flight power checks
./pre-flight-power.sh --all

# 2. Note which nodes have RAPL access
# 3. Proceed with Kepler deployment
# 4. After Kepler AND Scaphandre are deployed, validate
python kepler-validation-test.py --prometheus-url http://prometheus:9090
```

## Pre-Flight Checks Detail

### pre-flight-gpu.sh

Checks performed on each GPU worker node:

1. **nvidia-smi** - Basic GPU availability
2. **Kernel modules** - Driver compatibility with running kernel
3. **CUDA runtime** - CUDA toolkit availability
4. **Container runtime** - nvidia-container-toolkit configuration
5. **IOMMU** - GPU IOMMU group isolation
6. **GPU devices** - Device enumeration and count
7. **GPU baseline** - Current memory/utilization/temp/power
8. **VFIO** - Driver binding for passthrough

Exit code 0 = all critical checks pass, non-zero = failures detected.

### pre-flight-power.sh

Checks performed:

1. **RAPL sysfs** - /sys/class/powercap/intel-rapl exists
2. **RAPL domains** - Package, core, dram domains available
3. **RAPL readable** - Energy counter accessible
4. **RAPL functional** - Counter increments over time
5. **Powercap permissions** - World-readable vs sudo-required
6. **CPU info** - Intel vs AMD for RAPL support
7. **GPU power** - nvidia-smi power reading available
8. **Hypervisor RAPL** - Scaphandre fallback validation

## Rollback Script Detail

### gpu-operator-rollback.sh

Options:

| Flag | Action |
|------|--------|
| `--check` | Check current state only (no changes) |
| `--operator-only` | Remove operator, keep drivers |
| `--full` | Full rollback (default) |
| `--emergency` | Force cleanup (destructive) |

Actions performed:

1. Backup current state to timestamped directory
2. Uninstall Helm release (if Helm used)
3. Remove ClusterPolicy CR
4. Remove GPU Operator namespace
5. Remove NVIDIA CRDs
6. Clean node labels
7. Validate GPU still works on nodes

## Validation Test Detail

### kepler-validation-test.py

Checks performed:

1. **Kepler running** - Kepler targets UP in Prometheus
2. **Kepler container joules** - kepler_container_joules_total metric exists
3. **Kepler node power** - Non-zero power on nodes
4. **Scaphandre running** - Scaphandre targets UP
5. **Scaphandre host power** - scaph_host_power_microwatts metric
6. **Power comparison** - Kepler vs Scaphandre divergence < 30%
7. **Recording rules** - AK recording rules (ak:node_power_watts etc)

```bash
# Run with custom threshold
python kepler-validation-test.py --threshold 0.2  # 20% divergence

# Save report
python kepler-validation-test.py --output validation-report.json
```

## Swarm Analysis Source

These scripts address gaps identified by the adversarial swarm:

| Gap Identified | Script/Check |
|----------------|--------------|
| Rollback plan missing | `gpu-operator-rollback.sh` |
| nvidia-smi alone insufficient | `pre-flight-gpu.sh` (8 checks) |
| RAPL check alone insufficient | `pre-flight-power.sh` (8 checks) |
| Cross-validation missing | `kepler-validation-test.py` |
| Kernel module conflicts | `pre-flight-gpu.sh` check #2 |
| Nested virt RAPL issues | `pre-flight-power.sh` functional check |
| Performance baseline missing | `pre-flight-gpu.sh` check #7 |

## Files

```
scripts/safety/
├── README.md                    # This file
├── pre-flight-gpu.sh           # GPU compatibility checks
├── pre-flight-power.sh         # RAPL validation checks
├── gpu-operator-rollback.sh    # GPU Operator rollback
└── kepler-validation-test.py   # Power metric validation
```

## Related Documents

- [F10.2 Change Specs](../../../planning/features/F10_virtual_server_farm/F10.2_CHANGE_SPECS.md)
- [F10.2 Test Specs](../../../planning/features/F10_virtual_server_farm/F10.2_TEST_SPECS.md)
