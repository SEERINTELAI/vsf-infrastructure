"""
Report Generator

Generates experiment reports in various formats.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .statistics import StatisticalAnalyzer, DescriptiveStats, ConfidenceInterval

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates reports from experiment results.
    
    Supports:
    - JSON export
    - CSV export
    - Markdown report
    - Summary statistics
    """
    
    def __init__(self, output_dir: str | Path = "/tmp/vsf-reports"):
        self.output_dir = Path(output_dir)
        self.analyzer = StatisticalAnalyzer()
    
    def _ensure_output_dir(self, subdir: str = "") -> Path:
        """Ensure output directory exists."""
        path = self.output_dir / subdir if subdir else self.output_dir
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def export_json(
        self,
        experiment_result: dict,
        filename: str | None = None
    ) -> Path:
        """
        Export experiment result to JSON.
        
        Args:
            experiment_result: Experiment result dict
            filename: Optional filename (auto-generated if not provided)
            
        Returns:
            Path to generated file
        """
        output_dir = self._ensure_output_dir()
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = experiment_result.get("experiment_name", "experiment")
            filename = f"{name}_{timestamp}.json"
        
        output_path = output_dir / filename
        
        with open(output_path, "w") as f:
            json.dump(experiment_result, f, indent=2, default=str)
        
        logger.info(f"Exported JSON report: {output_path}")
        return output_path
    
    def export_csv(
        self,
        metrics: list[dict],
        filename: str,
        fields: list[str] | None = None
    ) -> Path:
        """
        Export metrics to CSV.
        
        Args:
            metrics: List of metric samples
            filename: Output filename
            fields: Optional list of fields to include
            
        Returns:
            Path to generated file
        """
        output_dir = self._ensure_output_dir()
        output_path = output_dir / filename
        
        if not metrics:
            raise ValueError("No metrics to export")
        
        # Determine fields
        if not fields:
            fields = list(metrics[0].keys())
        
        # Write CSV
        with open(output_path, "w") as f:
            f.write(",".join(fields) + "\n")
            for m in metrics:
                row = [str(m.get(field, "")) for field in fields]
                f.write(",".join(row) + "\n")
        
        logger.info(f"Exported CSV: {output_path}")
        return output_path
    
    def generate_summary(
        self,
        experiment_result: dict,
        baseline_phase: str = "baseline"
    ) -> dict[str, Any]:
        """
        Generate summary statistics for experiment.
        
        Args:
            experiment_result: Experiment result dict
            baseline_phase: Name of baseline phase
            
        Returns:
            Summary statistics dict
        """
        phases = experiment_result.get("phases", [])
        
        summary = {
            "experiment_name": experiment_result.get("experiment_name"),
            "started_at": experiment_result.get("started_at"),
            "ended_at": experiment_result.get("ended_at"),
            "status": experiment_result.get("status"),
            "phases_analyzed": len(phases),
            "comparisons": []
        }
        
        # Find baseline
        baseline = None
        for phase in phases:
            if phase.get("name") == baseline_phase:
                baseline = phase
                break
        
        if not baseline:
            summary["error"] = "Baseline phase not found"
            return summary
        
        baseline_metrics = baseline.get("metrics", [])
        
        # Compare each non-baseline phase
        for phase in phases:
            if phase.get("name") == baseline_phase:
                continue
            
            phase_metrics = phase.get("metrics", [])
            
            comparison = {
                "phase": phase.get("name"),
                "metrics": {}
            }
            
            # Calculate improvements for each metric
            for metric in ["power_watts", "energy_joules", "cpu_percent"]:
                baseline_values = [m.get(metric) for m in baseline_metrics if m.get(metric)]
                phase_values = [m.get(metric) for m in phase_metrics if m.get(metric)]
                
                if baseline_values and phase_values:
                    improvement, ci = self.analyzer.percent_improvement(
                        baseline_values, phase_values
                    )
                    
                    comparison["metrics"][metric] = {
                        "baseline_mean": round(sum(baseline_values) / len(baseline_values), 2),
                        "optimized_mean": round(sum(phase_values) / len(phase_values), 2),
                        "improvement_percent": round(improvement, 2),
                        "ci_lower": round(ci.lower, 2) if ci else None,
                        "ci_upper": round(ci.upper, 2) if ci else None
                    }
            
            summary["comparisons"].append(comparison)
        
        return summary
    
    def generate_markdown_report(
        self,
        experiment_result: dict,
        summary: dict | None = None
    ) -> str:
        """
        Generate Markdown report.
        
        Args:
            experiment_result: Experiment result dict
            summary: Optional pre-computed summary
            
        Returns:
            Markdown string
        """
        if not summary:
            summary = self.generate_summary(experiment_result)
        
        report = []
        report.append(f"# Experiment Report: {summary.get('experiment_name', 'Unknown')}")
        report.append("")
        report.append(f"**Date**: {summary.get('started_at', 'Unknown')}")
        report.append(f"**Status**: {summary.get('status', 'Unknown')}")
        report.append(f"**Phases Analyzed**: {summary.get('phases_analyzed', 0)}")
        report.append("")
        
        report.append("## Summary")
        report.append("")
        
        for comp in summary.get("comparisons", []):
            report.append(f"### Phase: {comp.get('phase')}")
            report.append("")
            report.append("| Metric | Baseline | Optimized | Improvement |")
            report.append("|--------|----------|-----------|-------------|")
            
            for metric, data in comp.get("metrics", {}).items():
                improvement = data.get("improvement_percent", 0)
                direction = "↓" if improvement > 0 else "↑"
                report.append(
                    f"| {metric} | {data.get('baseline_mean')} | "
                    f"{data.get('optimized_mean')} | "
                    f"{abs(improvement):.1f}% {direction} |"
                )
            
            report.append("")
        
        report.append("---")
        report.append(f"*Generated: {datetime.now().isoformat()}*")
        
        return "\n".join(report)
    
    def save_markdown_report(
        self,
        experiment_result: dict,
        filename: str | None = None
    ) -> Path:
        """Save Markdown report to file."""
        output_dir = self._ensure_output_dir()
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = experiment_result.get("experiment_name", "experiment")
            filename = f"{name}_{timestamp}.md"
        
        output_path = output_dir / filename
        
        summary = self.generate_summary(experiment_result)
        markdown = self.generate_markdown_report(experiment_result, summary)
        
        with open(output_path, "w") as f:
            f.write(markdown)
        
        logger.info(f"Saved Markdown report: {output_path}")
        return output_path
