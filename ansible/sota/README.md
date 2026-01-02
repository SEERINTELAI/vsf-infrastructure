# SOTA System Installation Playbooks

Ansible playbooks for installing third-party energy management systems.

## Systems

| System | Playbook | Purpose |
|--------|----------|---------|
| KEDA | `install-keda.yml` | Event-driven autoscaling |
| Intel PM | `install-intel-pm.yml` | Node power capping |
| Kube-green | `install-kube-green.yml` | Schedule-based suspension |

## Usage

```bash
# Install KEDA
ansible-playbook -i ../inventory/vsf.yml install-keda.yml

# Install Kube-green
ansible-playbook -i ../inventory/vsf.yml install-kube-green.yml

# Install Intel PM (may have limited functionality in VM)
ansible-playbook -i ../inventory/vsf.yml install-intel-pm.yml

# Install all Tier 1 systems
ansible-playbook -i ../inventory/vsf.yml install-keda.yml install-kube-green.yml install-intel-pm.yml
```

## KEDA

Event-driven autoscaling based on:
- Prometheus metrics
- CPU/Memory utilization
- Queue lengths

**CRDs**:
- `ScaledObject` - Autoscale Deployments
- `ScaledJob` - Autoscale Jobs
- `TriggerAuthentication` - Auth for triggers

## Kube-green

Schedule-based pod suspension for energy savings during off-hours.

**CRD**: `SleepInfo`

Example:
```yaml
apiVersion: kube-green.com/v1alpha1
kind: SleepInfo
metadata:
  name: nightly-sleep
spec:
  weekdays: "1-5"
  sleepAt: "20:00"
  wakeUpAt: "08:00"
  timeZone: "America/New_York"
```

## Intel PM

Node-level power management via P-states and C-states.

**Note**: Limited functionality in virtualized environments.

**CRD**: `PowerProfile`

Example:
```yaml
apiVersion: power.intel.com/v1
kind: PowerProfile
metadata:
  name: performance
spec:
  name: performance
  max: 100
  min: 80
  epp: performance
```

## VM Limitations

When running in a virtualized environment:
- Intel PM may not be able to control actual CPU frequency
- P-states/C-states controlled by hypervisor
- Power profiles may have no effect

The playbooks detect virtualization and:
1. Warn about limitations
2. Create status ConfigMap with info
3. Continue installation for API compatibility
