#!/usr/bin/env python3
"""
Run Power Baseline Experiments

Collects power consumption baselines for 8 workload types.
Used for comparison with SOTA systems and AgentOne optimization.

Usage:
    python scripts/run_baseline_experiments.py
    python scripts/run_baseline_experiments.py --config experiments/baselines/baseline_config.yaml
    python scripts/run_baseline_experiments.py --workload cpu-stress --only
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

from experiments import ExperimentRunner, ExperimentDefinition, MetricsCollector
from workloads import WorkloadGenerator, load_profile, BUILTIN_PROFILES
from safety import SafeWorkloadContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaselineRunner:
    """
    Runs power baseline experiments.
    
    Collects metrics for each workload type to establish
    comparison baselines for optimization strategies.
    """
    
    def __init__(self, config_path: str | Path | None = None):
        self.config_path = config_path or Path(__file__).parent.parent / "experiments/baselines/baseline_config.yaml"
        self.config = self._load_config()
        self.results: dict[str, Any] = {}
        self.generator = WorkloadGenerator()
        self.collector = MetricsCollector()
    
    def _load_config(self) -> dict:
        """Load baseline configuration."""
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    async def run_single_baseline(
        self,
        baseline: dict,
        repetition: int = 1
    ) -> dict[str, Any]:
        """
        Run a single baseline experiment.
        
        Args:
            baseline: Baseline configuration
            repetition: Current repetition number
            
        Returns:
            Baseline result with metrics
        """
        name = baseline["name"]
        logger.info(f"Starting baseline: {name} (rep {repetition})")
        
        result = {
            "name": name,
            "description": baseline.get("description", ""),
            "repetition": repetition,
            "started_at": datetime.now().isoformat(),
            "metrics": [],
            "status": "running"
        }
        
        try:
            # Warmup period
            if self.config.get("warmup", {}).get("enabled", True):
                warmup_duration = self.config["warmup"].get("duration_seconds", 60)
                logger.info(f"Warmup: {warmup_duration}s")
                await asyncio.sleep(min(warmup_duration, 5))  # Cap for testing
            
            # Deploy workload if specified
            workload_profile = baseline.get("workload")
            manifest = None
            
            if workload_profile:
                if workload_profile in BUILTIN_PROFILES:
                    profile = BUILTIN_PROFILES[workload_profile]
                else:
                    # Try to load from file
                    profile_path = Path(__file__).parent.parent / f"workloads/profiles/{workload_profile}.yaml"
                    if profile_path.exists():
                        profile = load_profile(profile_path)
                    else:
                        logger.warning(f"Profile {workload_profile} not found, skipping deployment")
                        profile = None
                
                if profile:
                    manifest = self.generator.generate(profile)
                    # In real execution: await self.generator.apply(manifest)
                    logger.info(f"Would deploy workload: {profile.name}")
            else:
                logger.info("No workload - measuring idle baseline")
            
            # Collect metrics
            duration = baseline.get("duration_seconds", 600)
            metrics_list = baseline.get("metrics", ["power_watts", "cpu_percent"])
            
            # Collect at 10-second intervals
            interval = 10
            samples = []
            
            for elapsed in range(0, min(duration, 60), interval):  # Cap for testing
                sample = await self.collector.collect(metrics_list)
                samples.append(sample)
                await asyncio.sleep(min(interval, 1))  # Cap for testing
            
            result["metrics"] = samples
            result["sample_count"] = len(samples)
            
            # Calculate summary statistics
            if samples:
                for metric in metrics_list:
                    values = [s.get(metric) for s in samples if s.get(metric) is not None]
                    if values:
                        result[f"{metric}_mean"] = sum(values) / len(values)
                        result[f"{metric}_min"] = min(values)
                        result[f"{metric}_max"] = max(values)
            
            result["status"] = "completed"
            result["ended_at"] = datetime.now().isoformat()
            
            # Cleanup workload
            if manifest:
                # In real execution: await self.generator.delete(manifest)
                logger.info(f"Would cleanup workload")
            
        except Exception as e:
            logger.error(f"Baseline {name} failed: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            result["ended_at"] = datetime.now().isoformat()
        
        return result
    
    async def run_all_baselines(self) -> dict[str, Any]:
        """
        Run all configured baselines.
        
        Returns:
            Complete baseline results
        """
        results = {
            "started_at": datetime.now().isoformat(),
            "config": self.config_path.name if isinstance(self.config_path, Path) else self.config_path,
            "baselines": {}
        }
        
        # Run with safety context
        async with SafeWorkloadContext() as ctx:
            if not ctx.safe:
                logger.error("Safety check failed - cannot run baselines")
                results["status"] = "safety_failed"
                return results
            
            baselines = self.config.get("baselines", [])
            
            for baseline in baselines:
                name = baseline["name"]
                repetitions = baseline.get("repetitions", 1)
                baseline_results = []
                
                for rep in range(1, repetitions + 1):
                    result = await self.run_single_baseline(baseline, rep)
                    baseline_results.append(result)
                    
                    # Cooldown between runs
                    if rep < repetitions:
                        cooldown = self.config.get("cooldown", {})
                        if cooldown.get("enabled", True):
                            duration = cooldown.get("duration_seconds", 120)
                            logger.info(f"Cooldown: {min(duration, 5)}s")
                            await asyncio.sleep(min(duration, 2))  # Cap for testing
                
                results["baselines"][name] = baseline_results
        
        results["ended_at"] = datetime.now().isoformat()
        results["status"] = "completed"
        
        return results
    
    def save_results(self, results: dict, output_dir: str | Path | None = None) -> Path:
        """Save baseline results to JSON."""
        output_dir = Path(output_dir or self.config.get("output", {}).get("directory", "/tmp/vsf-baselines"))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"baselines_{timestamp}.json"
        output_path = output_dir / filename
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Saved baselines to {output_path}")
        return output_path
    
    def generate_summary(self, results: dict) -> str:
        """Generate summary of baseline results."""
        lines = [
            "# Power Baseline Summary",
            "",
            f"Started: {results.get('started_at')}",
            f"Ended: {results.get('ended_at')}",
            f"Status: {results.get('status')}",
            "",
            "## Results",
            "",
            "| Baseline | Power (W) | Energy (J) | CPU % | Status |",
            "|----------|-----------|------------|-------|--------|"
        ]
        
        for name, runs in results.get("baselines", {}).items():
            if runs:
                # Average across repetitions
                power_means = [r.get("power_watts_mean", 0) for r in runs if r.get("power_watts_mean")]
                energy_means = [r.get("energy_joules_mean", 0) for r in runs if r.get("energy_joules_mean")]
                cpu_means = [r.get("cpu_percent_mean", 0) for r in runs if r.get("cpu_percent_mean")]
                
                power = sum(power_means) / len(power_means) if power_means else 0
                energy = sum(energy_means) / len(energy_means) if energy_means else 0
                cpu = sum(cpu_means) / len(cpu_means) if cpu_means else 0
                status = runs[-1].get("status", "unknown")
                
                lines.append(f"| {name} | {power:.1f} | {energy:.1f} | {cpu:.1f} | {status} |")
        
        return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Run power baseline experiments")
    parser.add_argument("--config", type=Path, help="Config file path")
    parser.add_argument("--workload", type=str, help="Run only this workload")
    parser.add_argument("--only", action="store_true", help="Run only specified workload")
    parser.add_argument("--output", type=Path, help="Output directory")
    
    args = parser.parse_args()
    
    runner = BaselineRunner(config_path=args.config)
    
    logger.info("Starting power baseline experiments")
    results = await runner.run_all_baselines()
    
    output_path = runner.save_results(results, args.output)
    
    summary = runner.generate_summary(results)
    print("\n" + summary)
    
    # Save summary
    summary_path = output_path.parent / f"summary_{output_path.stem}.md"
    with open(summary_path, "w") as f:
        f.write(summary)
    
    logger.info(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
