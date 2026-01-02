# VSF System Probe Deployment

This directory contains Ansible playbooks for deploying the System Probe MCP server to all 21 Virtual Server Farm VMs.

## Overview

Each VSF VM runs a System Probe that provides node-level optimization controls:
- CPU governor management
- I/O scheduling control
- System metrics collection
- MCP endpoint for AgentOne integration

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentOne                                       │
│                (Optimization Controller)                            │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ MCP (Multi-Probe Router)
          ┌───────────────┼───────────────┬───────────────┐
          │               │               │               │
          ▼               ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
    │vsf-cp-1 │     │vsf-cp-2 │     │worker-1 │     │gpu-1    │
    │  :8765  │     │  :8765  │     │  :8765  │     │  :8765  │
    │ SysProbe│     │ SysProbe│     │ SysProbe│     │ SysProbe│
    └─────────┘     └─────────┘     └─────────┘     └─────────┘
          │               │               │               │
          └───────────────┴───────────────┴───────────────┘
                              21 Probes Total
```

## Files

| File | Purpose |
|------|---------|
| `package-system-probe.sh` | Packages Zon-data-center probe for VM deployment |
| `deploy-system-probes.yml` | Main deployment playbook |
| `validate-probes.yml` | Validates probe health on all VMs |
| `templates/system-probe.service.j2` | Systemd service template |
| `dist/` | Generated packages (gitignored) |

## Prerequisites

1. Ansible installed on control node
2. SSH access to all VSF VMs
3. `Zon-data-center` repo available at `~/ASIT/repos/Zon-data-center`
4. Python 3.11+ on all VMs

## Usage

### Full Deployment

```bash
cd /home/dan/ASIT/repos/vsf-infrastructure/ansible

# Deploy to all VMs
ansible-playbook -i inventory/vsf.yml probes/deploy-system-probes.yml

# Deploy to specific group
ansible-playbook -i inventory/vsf.yml probes/deploy-system-probes.yml --limit workers

# Deploy with verbose output
ansible-playbook -i inventory/vsf.yml probes/deploy-system-probes.yml -v
```

### Validate Deployment

```bash
ansible-playbook -i inventory/vsf.yml probes/validate-probes.yml
```

### Manual Packaging (Development)

```bash
cd probes/
ZDC_PATH=/path/to/Zon-data-center ./package-system-probe.sh
```

## VM Configuration

Each probe is configured with:

| Setting | Value | Reason |
|---------|-------|--------|
| `DISABLE_GPU=true` | Disabled | VMs don't have real GPUs |
| `DISABLE_RAPL=true` | Disabled | RAPL not available in VMs |
| `MCP_PORT=8765` | Default | Standard MCP port |

## Probe Endpoints

After deployment, each VM exposes:

- **MCP Endpoint**: `http://<vm-ip>:8765/mcp`
- **Health Check**: `http://<vm-ip>:8765/health` (if implemented)

### Available Tools

| Tool | Description | VM Support |
|------|-------------|------------|
| `get_cpu_governor` | Get current CPU governor | ✅ Full |
| `set_cpu_governor` | Set CPU governor | ✅ Full |
| `get_io_scheduler` | Get I/O scheduler | ✅ Full |
| `set_io_scheduling` | Set I/O priority | ✅ Full |
| `snapshot_power` | Power measurement | ⚠️ Estimated |
| `nvml_stats` | GPU metrics | ❌ N/A |
| `system_info` | System information | ✅ Full |
| `running_processes` | Process list | ✅ Full |

## Service Management

On each VM:

```bash
# Start probe
sudo systemctl start system-probe

# Stop probe
sudo systemctl stop system-probe

# Check status
sudo systemctl status system-probe

# View logs
sudo journalctl -u system-probe -f
```

## Probe Discovery

All probes register themselves with n8n webhook on startup. The registration includes:
- Hostname
- MCP endpoint URL
- System information

Configure `N8N_WEBHOOK_URL` in `/opt/system-probe/config.env` for registration.

## Troubleshooting

### Probe won't start

```bash
# Check service logs
sudo journalctl -u system-probe -n 50

# Check Python environment
/opt/system-probe/venv/bin/python3 --version

# Test manual start
cd /opt/system-probe
source venv/bin/activate
python3 -m mcp_server.zon_mcp_server --port 8765
```

### Port already in use

```bash
# Find process using port
sudo lsof -i :8765

# Kill if needed
sudo kill -9 <PID>
```

### Permission issues

```bash
# Fix ownership
sudo chown -R probe:probe /opt/system-probe

# Fix permissions
sudo chmod +x /opt/system-probe/start-probe-vm.sh
```

## Updates

To update probes on all VMs:

```bash
# Re-run deployment (will overwrite)
ansible-playbook -i inventory/vsf.yml probes/deploy-system-probes.yml

# Or use the probe's built-in update (if configured)
# via MCP: update_probe()
```

## Security Notes

- Probes run as non-root user `probe`
- Systemd service has security hardening (NoNewPrivileges, etc.)
- MCP endpoint should be accessed only from trusted networks
- Consider firewall rules in production
