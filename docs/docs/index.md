# VSF Infrastructure

Welcome to the Virtual Server Farm (VSF) Infrastructure documentation.

## Overview

The VSF is a 24-node virtualized Kubernetes cluster on Bizon1 for energy optimization testing.

## Quick Links

- [Getting Started](getting-started.md) - Setup guide
- [Architecture](architecture.md) - System design

## Infrastructure Summary

| Component | Count | Resources |
|-----------|-------|-----------|
| Control Plane | 3 | 8 vCPU, 32GB RAM each |
| Workers | 10 | 4 vCPU, 16GB RAM each |
| GPU Workers | 8 | 8 vCPU, 32GB RAM, 1 GPU each |
| Infrastructure | 3 | Prometheus, DNS, Storage |
| **Total** | **24** | **~140 vCPU, ~640GB RAM** |
