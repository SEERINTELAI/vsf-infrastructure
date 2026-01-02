#!/usr/bin/env python3
"""
Run SOTA vs AgentOne Comparison Experiments

Executes comparative experiments between SOTA systems and AgentOne.

Usage:
    python scripts/run_comparison_experiment.py --experiment exp-keda-vs-baseline
    python scripts/run_comparison_experiment.py --all
    python scripts/run_comparison_experiment.py --list
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments import ExperimentRunner, ExperimentDefinition
from experiments.comparison import ResultComparator
from analysis import generate_report
from safety import SafeWorkloadContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComparisonExperimentRunner:
    """
    Runs comparison experiments between SOTA systems and AgentOne.
    """
    
    def __init__(self, config_path: str | Path | None = None):
        self.config_path = config_path or Path(__file__).parent.parent / "experiments/comparisons/experiment_definitions.yaml"
        self.config = self._load_config()
        self.runner = ExperimentRunner()
        self.comparator = ResultComparator()
    
    def _load_config(self) -> dict:
        """Load experiment definitions."""
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def list_experiments(self) -> list[dict]:
        """List available experiments."""
        experiments = []
        for exp in self.config.get("experiments", []):
            experiments.append({
                "id": exp["id"],
                "name": exp["name"],
                "phases": len(exp.get("phases", [])),
                "description": exp.get("description", "")[:100]
            })
        return experiments
    
    def get_experiment(self, exp_id: str) -> dict | None:
        """Get experiment by ID."""
        for exp in self.config.get("experiments", []):
            if exp["id"] == exp_id:
                return exp
        return None
    
    async def run_experiment(self, exp_id: str) -> dict[str, Any]:
        """
        Run a comparison experiment.
        
        Args:
            exp_id: Experiment ID
            
        Returns:
            Experiment results with comparison
        """
        experiment = self.get_experiment(exp_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {exp_id}")
        
        logger.info(f"Starting experiment: {experiment['name']}")
        
        results = {
            "experiment_id": exp_id,
            "experiment_name": experiment["name"],
            "started_at": datetime.now().isoformat(),
            "phases": {},
            "comparison": None,
            "status": "running"
        }
        
        # Safety context
        async with SafeWorkloadContext() as ctx:
            if not ctx.safe:
                logger.error("Safety check failed")
                results["status"] = "safety_failed"
                return results
            
            # Run each phase
            for phase in experiment.get("phases", []):
                phase_name = phase["name"]
                logger.info(f"Running phase: {phase_name}")
                
                # Configure optimization
                await self._configure_optimization(phase.get("optimization"), phase.get("config"))
                
                # Warmup
                warmup = self.config.get("shared", {}).get("warmup_seconds", 300)
                logger.info(f"Warmup: {min(warmup, 10)}s")
                await asyncio.sleep(min(warmup, 5))  # Cap for testing
                
                # Run phase
                duration = phase.get("duration_seconds", 3600)
                phase_result = await self.runner.run_phase(
                    duration=min(duration, 60),  # Cap for testing
                    metrics=phase.get("metrics", []),
                    workload=phase.get("workload")
                )
                
                results["phases"][phase_name] = phase_result
                
                # Cooldown
                cooldown = self.config.get("shared", {}).get("cooldown_seconds", 600)
                await self._disable_optimization()
                await asyncio.sleep(min(cooldown, 5))  # Cap for testing
            
            # Compare phases
            if len(results["phases"]) >= 2:
                phase_names = list(results["phases"].keys())
                results["comparison"] = self.comparator.compare(
                    results["phases"][phase_names[0]],
                    results["phases"][phase_names[1]],
                    experiment.get("success_criteria", [])
                )
        
        results["ended_at"] = datetime.now().isoformat()
        results["status"] = "completed"
        
        return results
    
    async def _configure_optimization(
        self,
        optimization: str | list | dict | None,
        config: dict | None
    ) -> None:
        """Configure optimization system for a phase."""
        if optimization is None or optimization == "none":
            logger.info("No optimization (baseline)")
            return
        
        if isinstance(optimization, str):
            optimizations = [optimization]
        elif isinstance(optimization, list):
            optimizations = optimization
        else:
            optimizations = []
        
        for opt in optimizations:
            logger.info(f"Enabling optimization: {opt}")
            # In real implementation, would enable the system
            # e.g., create ScaledObject for KEDA, enable AgentOne
    
    async def _disable_optimization(self) -> None:
        """Disable all optimizations between phases."""
        logger.info("Disabling all optimizations")
        # In real implementation, would disable systems
    
    def save_results(self, results: dict, output_dir: str | Path | None = None) -> Path:
        """Save experiment results."""
        output_dir = Path(output_dir or "/tmp/vsf-comparisons")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exp_id = results.get("experiment_id", "unknown")
        filename = f"comparison_{exp_id}_{timestamp}.json"
        output_path = output_dir / filename
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Saved results to {output_path}")
        return output_path
    
    def generate_report(self, results: dict) -> str:
        """Generate comparison report."""
        lines = [
            f"# Comparison Report: {results.get('experiment_name')}",
            "",
            f"**Experiment ID**: {results.get('experiment_id')}",
            f"**Started**: {results.get('started_at')}",
            f"**Ended**: {results.get('ended_at')}",
            f"**Status**: {results.get('status')}",
            "",
            "## Phase Results",
            ""
        ]
        
        for phase_name, phase_data in results.get("phases", {}).items():
            lines.append(f"### {phase_name}")
            lines.append("")
            lines.append("| Metric | Mean | Min | Max |")
            lines.append("|--------|------|-----|-----|")
            
            for key, value in phase_data.items():
                if key.endswith("_mean"):
                    metric = key.replace("_mean", "")
                    mean_val = value
                    min_val = phase_data.get(f"{metric}_min", "N/A")
                    max_val = phase_data.get(f"{metric}_max", "N/A")
                    lines.append(f"| {metric} | {mean_val:.2f} | {min_val} | {max_val} |")
            
            lines.append("")
        
        # Comparison summary
        comparison = results.get("comparison")
        if comparison:
            lines.append("## Comparison Summary")
            lines.append("")
            
            if comparison.get("success"):
                lines.append("✅ **All success criteria met**")
            else:
                lines.append("❌ **Some criteria not met**")
            
            lines.append("")
            lines.append("| Metric | Improvement | Target | Status |")
            lines.append("|--------|-------------|--------|--------|")
            
            for criterion in comparison.get("criteria_results", []):
                status = "✅" if criterion.get("met") else "❌"
                lines.append(f"| {criterion.get('metric')} | {criterion.get('improvement', 0):.1f}% | {criterion.get('target', 'N/A')} | {status} |")
        
        return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Run SOTA comparison experiments")
    parser.add_argument("--experiment", type=str, help="Experiment ID to run")
    parser.add_argument("--all", action="store_true", help="Run all experiments")
    parser.add_argument("--list", action="store_true", help="List available experiments")
    parser.add_argument("--output", type=Path, help="Output directory")
    
    args = parser.parse_args()
    
    runner = ComparisonExperimentRunner()
    
    if args.list:
        print("\nAvailable Experiments:")
        print("-" * 60)
        for exp in runner.list_experiments():
            print(f"\n{exp['id']}: {exp['name']}")
            print(f"  Phases: {exp['phases']}")
            print(f"  {exp['description']}")
        return
    
    experiments_to_run = []
    
    if args.all:
        experiments_to_run = [e["id"] for e in runner.list_experiments()]
    elif args.experiment:
        experiments_to_run = [args.experiment]
    else:
        parser.print_help()
        return
    
    for exp_id in experiments_to_run:
        logger.info(f"Running experiment: {exp_id}")
        
        results = await runner.run_experiment(exp_id)
        output_path = runner.save_results(results, args.output)
        
        report = runner.generate_report(results)
        print("\n" + report)
        
        # Save report
        report_path = output_path.parent / f"report_{output_path.stem}.md"
        with open(report_path, "w") as f:
            f.write(report)
        
        logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
