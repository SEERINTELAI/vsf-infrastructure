"""
Workload Profile Definitions

Defines the structure for workload profiles and built-in profiles
for different workload patterns (steady-state, bursty, diurnal, etc.)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, validator


class ResourceSpec(BaseModel):
    """Resource requests/limits for containers."""
    cpu: str = "100m"
    memory: str = "128Mi"
    gpu: str | None = Field(None, alias="nvidia.com/gpu")
    
    class Config:
        populate_by_name = True


class Resources(BaseModel):
    """Container resources."""
    requests: ResourceSpec
    limits: ResourceSpec


class WorkloadProfile(BaseModel):
    """
    Workload profile definition.
    
    Defines how a workload should be generated and controlled.
    """
    name: str
    type: str = "deployment"  # deployment, job, daemonset
    namespace: str = "vsf-workloads"
    replicas: int = 1
    parallelism: int | None = None  # For jobs
    completions: int | None = None  # For jobs
    resources: Resources
    intensity: float = Field(0.5, ge=0.0, le=0.8)  # Capped at 0.8 for safety
    pattern: str = "steady-state"
    duration_seconds: int = 300
    image: str = "busybox:1.36"
    command: list[str] = Field(default_factory=lambda: ["sh", "-c", "while true; do :; done"])
    node_selector: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    tolerations: list[dict] = Field(default_factory=list)
    
    @validator("intensity")
    def clamp_intensity(cls, v):
        """Clamp intensity to safety maximum of 0.8."""
        return min(max(v, 0.0), 0.8)
    
    @validator("labels", pre=True, always=True)
    def ensure_vsf_label(cls, v):
        """Ensure vsf-workload label is present."""
        v = v or {}
        v["vsf-workload"] = "true"
        return v


def load_profile(path: str | Path) -> WorkloadProfile:
    """
    Load a workload profile from YAML file.
    
    Args:
        path: Path to YAML profile file
        
    Returns:
        WorkloadProfile instance
        
    Raises:
        yaml.YAMLError: If YAML is malformed
        ValidationError: If profile is invalid
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    
    return WorkloadProfile(**data)


# =============================================================================
# Built-in Profiles
# =============================================================================

BUILTIN_PROFILES = {
    "steady-state": WorkloadProfile(
        name="steady-state-workload",
        type="deployment",
        replicas=5,
        resources=Resources(
            requests=ResourceSpec(cpu="100m", memory="128Mi"),
            limits=ResourceSpec(cpu="500m", memory="512Mi")
        ),
        intensity=0.5,
        pattern="steady-state",
        duration_seconds=600
    ),
    
    "bursty": WorkloadProfile(
        name="bursty-workload",
        type="deployment",
        replicas=10,
        resources=Resources(
            requests=ResourceSpec(cpu="200m", memory="256Mi"),
            limits=ResourceSpec(cpu="1", memory="1Gi")
        ),
        intensity=0.7,
        pattern="bursty",
        duration_seconds=300
    ),
    
    "diurnal": WorkloadProfile(
        name="diurnal-workload",
        type="deployment",
        replicas=8,
        resources=Resources(
            requests=ResourceSpec(cpu="150m", memory="192Mi"),
            limits=ResourceSpec(cpu="750m", memory="768Mi")
        ),
        intensity=0.6,
        pattern="diurnal",
        duration_seconds=900
    ),
    
    "batch-gpu": WorkloadProfile(
        name="gpu-batch-workload",
        type="job",
        replicas=1,
        parallelism=4,
        completions=8,
        resources=Resources(
            requests=ResourceSpec(cpu="500m", memory="1Gi", gpu="1"),
            limits=ResourceSpec(cpu="2", memory="4Gi", gpu="1")
        ),
        intensity=0.8,
        pattern="batch-gpu",
        duration_seconds=600,
        image="nvcr.io/nvidia/cuda:12.0-base",
        command=["sh", "-c", "nvidia-smi && sleep 60"],
        node_selector={"gpu": "true"},
        tolerations=[{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}]
    ),
    
    "mixed": WorkloadProfile(
        name="mixed-workload",
        type="deployment",
        replicas=6,
        resources=Resources(
            requests=ResourceSpec(cpu="120m", memory="160Mi"),
            limits=ResourceSpec(cpu="600m", memory="640Mi")
        ),
        intensity=0.55,
        pattern="mixed",
        duration_seconds=450
    )
}
