# Mock DCGM Exporter

A Helm chart that deploys a mock NVIDIA DCGM Exporter for the Virtual Server Farm (VSF). This provides synthetic GPU metrics in Prometheus format, matching the schema of the real DCGM Exporter for seamless upgrade path.

## Purpose

This is a **mock mode** component designed for:
- Safe development and testing without real GPU hardware
- Fast iteration on monitoring dashboards and alerts
- Validating Prometheus/Grafana integration
- Testing GPU-aware workload scheduling

## Installation

```bash
helm install mock-dcgm-exporter ./helm/mock-dcgm-exporter \
  --namespace gpu-monitoring \
  --create-namespace
```

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gpuSimulation.gpusPerNode` | Number of GPUs to simulate per node | `1` |
| `gpuSimulation.gpuModel` | GPU model name to report | `NVIDIA RTX 4090` |
| `gpuSimulation.gpuMemoryMiB` | GPU memory in MiB | `24576` |
| `gpuSimulation.defaultProfile` | Workload profile (idle/moderate/heavy) | `moderate` |
| `metrics.port` | Prometheus metrics port | `9400` |
| `serviceMonitor.enabled` | Create ServiceMonitor for Prometheus Operator | `true` |

### Workload Profiles

| Profile | GPU Util | Memory Used | Power Draw | Temp |
|---------|----------|-------------|------------|------|
| `idle` | 0-5% | 500-1000 MiB | 50-80W | 35-45°C |
| `moderate` | 20-60% | 4-12 GB | 150-280W | 55-70°C |
| `heavy` | 80-100% | 18-23 GB | 350-450W | 70-85°C |

## Metrics Exposed

Matches real DCGM Exporter metrics:

- `DCGM_FI_DEV_GPU_UTIL` - GPU utilization (%)
- `DCGM_FI_DEV_MEM_COPY_UTIL` - Memory utilization (%)
- `DCGM_FI_DEV_FB_FREE` - Framebuffer free (MiB)
- `DCGM_FI_DEV_FB_USED` - Framebuffer used (MiB)
- `DCGM_FI_DEV_POWER_USAGE` - Power draw (W)
- `DCGM_FI_DEV_GPU_TEMP` - Temperature (°C)
- `DCGM_FI_DEV_SM_CLOCK` - SM clock (MHz)
- `DCGM_FI_DEV_MEM_CLOCK` - Memory clock (MHz)
- `DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION` - Total energy (mJ)

## Upgrade Path to Real GPU Monitoring

When ready to use real GPU hardware:

1. **Uninstall mock exporter**:
   ```bash
   helm uninstall mock-dcgm-exporter -n gpu-monitoring
   ```

2. **Install NVIDIA GPU Operator**:
   ```bash
   helm install gpu-operator nvidia/gpu-operator \
     --namespace gpu-operator \
     --create-namespace \
     --set dcgmExporter.enabled=true
   ```

3. **Update Grafana dashboards**: No changes needed (same metric names)

4. **Update Prometheus scrape configs**: Update ServiceMonitor selector if needed

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ GPU Node (vsf-gpu-*)                                        │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ mock-dcgm-exporter Pod                                  │ │
│ │ ┌─────────────────┐   ┌────────────────────────────┐   │ │
│ │ │ Python Script   │──▶│ :9400/metrics              │   │ │
│ │ │ (ConfigMap)     │   │ Prometheus format          │   │ │
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
                    │ (GPU Dashboard) │
                    └─────────────────┘
```

## Testing

```bash
# Port-forward to test locally
kubectl port-forward svc/mock-dcgm-exporter 9400:9400 -n gpu-monitoring

# Curl metrics
curl http://localhost:9400/metrics
```
