# Synthetic Power Exporter

A Helm chart that deploys a synthetic power exporter for the Virtual Server Farm (VSF). This provides Kepler-compatible power metrics using formula-based estimation, enabling power monitoring development without RAPL hardware access.

## Purpose

This is a **mock mode** component designed for:
- Development and testing without RAPL access
- Validating power monitoring dashboards
- Testing energy-aware scheduling logic
- Simulating per-container power consumption

## Installation

```bash
helm install synthetic-power-exporter ./helm/synthetic-power-exporter \
  --namespace power-monitoring \
  --create-namespace
```

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `powerSimulation.basePowerWatts` | Idle power consumption | `50` |
| `powerSimulation.cpuPowerFactor` | Watts per CPU % | `2.5` |
| `powerSimulation.memoryPowerFactor` | Watts per GB RAM | `0.5` |
| `powerSimulation.maxNodePowerWatts` | Maximum node power | `500` |
| `powerSimulation.defaultProfile` | Workload profile | `moderate` |
| `metrics.port` | Prometheus metrics port | `9100` |
| `serviceMonitor.enabled` | Create ServiceMonitor | `true` |

### Power Estimation Formula

```
node_power = base_power + (cpu_util * cpu_factor) + (memory_gb * memory_factor)
```

With defaults: `50W + (50% * 2.5) + (16GB * 0.5) = 50 + 125 + 8 = 183W`

## Metrics Exposed

Matches Kepler metrics schema:

**Node-level:**
- `kepler_node_core_joules_total` - CPU core energy
- `kepler_node_dram_joules_total` - DRAM energy
- `kepler_node_package_joules_total` - CPU package energy
- `kepler_node_platform_joules_total` - Platform total energy
- `node_power_watts` - Current power draw
- `node_cpu_utilization_percent` - CPU utilization

**Container-level:**
- `kepler_container_joules_total` - Container total energy
- `kepler_container_core_joules_total` - Container CPU energy
- `kepler_container_dram_joules_total` - Container DRAM energy

## Upgrade Path to Real Power Monitoring

When ready to use real RAPL hardware:

1. **Verify RAPL access**:
   ```bash
   ls /sys/class/powercap/intel-rapl/
   ```

2. **Run pre-flight checks**:
   ```bash
   ./scripts/safety/pre-flight-power.sh
   ```

3. **Uninstall synthetic exporter**:
   ```bash
   helm uninstall synthetic-power-exporter -n power-monitoring
   ```

4. **Install Kepler**:
   ```bash
   helm install kepler kepler/kepler \
     --namespace kepler \
     --create-namespace
   ```

5. **Update Prometheus scrape configs** if needed

6. **Grafana dashboards**: Same metric names, no changes needed

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ All Nodes (DaemonSet)                                       │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ synthetic-power-exporter Pod                            │ │
│ │ ┌─────────────────┐   ┌────────────────────────────┐   │ │
│ │ │ Python Script   │──▶│ :9100/metrics              │   │ │
│ │ │ (Formula-based) │   │ Kepler-compatible          │   │ │
│ │ └─────────────────┘   └────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Prometheus      │
                    │ (ServiceMonitor)│
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Grafana         │
                    │ (Power Dashboard)│
                    └─────────────────┘
```

## Testing

```bash
# Port-forward to test locally
kubectl port-forward svc/synthetic-power-exporter 9100:9100 -n power-monitoring

# Curl metrics
curl http://localhost:9100/metrics
```
