"""
Experiment Runner

Executes experiment phases and collects metrics.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .definition import ExperimentDefinition, Phase
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class PhaseResult:
    """Result of a single phase execution."""
    phase_name: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    metrics: list[dict[str, Any]]
    status: str  # completed, failed, cancelled
    error: str | None = None


@dataclass
class ExperimentResult:
    """Complete experiment result."""
    experiment_name: str
    started_at: datetime
    ended_at: datetime | None = None
    phase_results: list[PhaseResult] = field(default_factory=list)
    repetition: int = 1
    status: str = "running"  # running, completed, failed, cancelled
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "experiment_name": self.experiment_name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "repetition": self.repetition,
            "phases": [
                {
                    "name": pr.phase_name,
                    "started_at": pr.started_at.isoformat(),
                    "ended_at": pr.ended_at.isoformat(),
                    "duration_seconds": pr.duration_seconds,
                    "metrics_count": len(pr.metrics),
                    "status": pr.status,
                    "error": pr.error
                }
                for pr in self.phase_results
            ]
        }


class ExperimentRunner:
    """
    Runs experiments with workload generation and metrics collection.
    
    Usage:
        runner = ExperimentRunner(experiment)
        result = await runner.run()
    """
    
    def __init__(
        self,
        experiment: ExperimentDefinition,
        metrics_collector: MetricsCollector | None = None,
        on_phase_complete: Callable[[PhaseResult], None] | None = None
    ):
        self.experiment = experiment
        self.metrics = metrics_collector or MetricsCollector()
        self.on_phase_complete = on_phase_complete
        self._running = False
        self._cancelled = False
    
    async def _apply_optimization(self, phase: Phase) -> None:
        """Apply optimization settings for phase."""
        if phase.optimization is None:
            logger.info(f"Phase {phase.name}: No optimization (baseline)")
            return
        
        opt = phase.optimization
        
        if opt.cpu_governor:
            logger.info(f"Setting CPU governor to {opt.cpu_governor}")
            # Would call MCP here: await mcp.set_cpu_governor(opt.cpu_governor)
        
        if opt.gpu_power_limit:
            logger.info(f"Setting GPU power limit to {opt.gpu_power_limit}W")
            # Would call MCP here: await mcp.set_gpu_power_cap(opt.gpu_power_limit)
        
        if opt.io_scheduler:
            logger.info(f"Setting I/O scheduler to {opt.io_scheduler}")
            # Would call MCP here: await mcp.set_io_scheduler(opt.io_scheduler)
    
    async def _run_phase(self, phase: Phase) -> PhaseResult:
        """Run a single experiment phase."""
        logger.info(f"Starting phase: {phase.name}")
        started_at = datetime.now()
        
        try:
            # Apply optimizations
            await self._apply_optimization(phase)
            
            # Warmup period
            if phase.warmup_seconds > 0:
                logger.info(f"Warmup period: {phase.warmup_seconds}s")
                await asyncio.sleep(min(phase.warmup_seconds, 5))  # Cap for testing
            
            # Start metrics collection
            metrics = []
            collection_interval = 10  # seconds
            
            for elapsed in range(0, phase.duration_seconds, collection_interval):
                if self._cancelled:
                    raise asyncio.CancelledError()
                
                # Collect metrics
                sample = await self.metrics.collect(self.experiment.metrics)
                metrics.append(sample)
                
                # Wait for next interval (capped for testing)
                await asyncio.sleep(min(collection_interval, 1))
            
            ended_at = datetime.now()
            
            return PhaseResult(
                phase_name=phase.name,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=(ended_at - started_at).total_seconds(),
                metrics=metrics,
                status="completed"
            )
            
        except asyncio.CancelledError:
            return PhaseResult(
                phase_name=phase.name,
                started_at=started_at,
                ended_at=datetime.now(),
                duration_seconds=(datetime.now() - started_at).total_seconds(),
                metrics=[],
                status="cancelled"
            )
        except Exception as e:
            logger.error(f"Phase {phase.name} failed: {e}")
            return PhaseResult(
                phase_name=phase.name,
                started_at=started_at,
                ended_at=datetime.now(),
                duration_seconds=(datetime.now() - started_at).total_seconds(),
                metrics=[],
                status="failed",
                error=str(e)
            )
    
    async def run(self, repetition: int = 1) -> ExperimentResult:
        """
        Run the complete experiment.
        
        Args:
            repetition: Current repetition number (1-based)
            
        Returns:
            ExperimentResult with all phase results
        """
        self._running = True
        self._cancelled = False
        
        result = ExperimentResult(
            experiment_name=self.experiment.name,
            started_at=datetime.now(),
            repetition=repetition
        )
        
        logger.info(f"Starting experiment: {self.experiment.name} (rep {repetition})")
        
        try:
            for phase in self.experiment.phases:
                if self._cancelled:
                    break
                
                phase_result = await self._run_phase(phase)
                result.phase_results.append(phase_result)
                
                if self.on_phase_complete:
                    self.on_phase_complete(phase_result)
                
                if phase_result.status == "failed":
                    result.status = "failed"
                    break
            else:
                result.status = "completed"
            
            if self._cancelled:
                result.status = "cancelled"
            
        finally:
            result.ended_at = datetime.now()
            self._running = False
        
        logger.info(f"Experiment {self.experiment.name} finished: {result.status}")
        return result
    
    async def run_all_repetitions(self) -> list[ExperimentResult]:
        """Run all repetitions of the experiment."""
        results = []
        
        for rep in range(1, self.experiment.repetitions + 1):
            logger.info(f"Repetition {rep}/{self.experiment.repetitions}")
            result = await self.run(repetition=rep)
            results.append(result)
            
            if result.status == "failed":
                logger.warning("Stopping due to failure")
                break
        
        return results
    
    def cancel(self) -> None:
        """Cancel the running experiment."""
        self._cancelled = True
        logger.info("Experiment cancellation requested")
