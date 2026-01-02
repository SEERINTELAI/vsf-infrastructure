"""
Experiment Definition Models

Pydantic models for experiment definitions.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, validator


class Optimization(BaseModel):
    """Optimization settings for a phase."""
    cpu_governor: str | None = None
    gpu_power_limit: int | None = None
    io_scheduler: str | None = None
    custom: dict[str, Any] = Field(default_factory=dict)


class Phase(BaseModel):
    """Experiment phase definition."""
    name: str
    duration_seconds: int = Field(ge=10, le=3600)
    workload: str = "steady-state"
    optimization: Optimization | None = None
    warmup_seconds: int = 30
    
    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Phase name cannot be empty")
        return v


class ExperimentDefinition(BaseModel):
    """
    Complete experiment definition.
    
    Usage:
        exp = ExperimentDefinition.from_yaml("experiment.yaml")
        print(exp.phases)
    """
    name: str
    description: str = ""
    phases: list[Phase] = Field(min_items=1)
    metrics: list[str] = Field(min_items=1)
    repetitions: int = Field(1, ge=1, le=10)
    output_dir: Path = Path("/tmp/vsf-experiments")
    created_at: datetime = Field(default_factory=datetime.now)
    
    @validator("metrics")
    def validate_metrics(cls, v):
        valid_metrics = {
            "power_watts", "energy_joules", "cpu_percent",
            "memory_percent", "gpu_power", "gpu_temp",
            "io_read_bytes", "io_write_bytes"
        }
        invalid = set(v) - valid_metrics
        if invalid:
            raise ValueError(f"Unknown metrics: {invalid}")
        return v
    
    @classmethod
    def from_yaml(cls, path: str | Path) -> "ExperimentDefinition":
        """Load experiment from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def to_yaml(self, path: str | Path) -> None:
        """Save experiment to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.dict(), f, default_flow_style=False)
    
    @property
    def total_duration_seconds(self) -> int:
        """Total experiment duration across all phases and repetitions."""
        phase_duration = sum(p.duration_seconds + p.warmup_seconds for p in self.phases)
        return phase_duration * self.repetitions
    
    @property
    def baseline_phase(self) -> Phase | None:
        """Find the baseline phase (no optimization)."""
        for phase in self.phases:
            if phase.optimization is None:
                return phase
        return None
