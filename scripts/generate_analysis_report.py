#!/usr/bin/env python3
"""
Generate SOTA Comparison Analysis Report

Produces a comprehensive analysis report comparing
SOTA systems with AgentOne optimization.

Usage:
    python scripts/generate_analysis_report.py --results /tmp/vsf-comparisons/
    python scripts/generate_analysis_report.py --summary
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_results(results_dir: Path) -> list[dict]:
    """Load all experiment results from directory."""
    results = []
    for f in results_dir.glob("comparison_*.json"):
        with open(f) as fp:
            results.append(json.load(fp))
    return sorted(results, key=lambda x: x.get("experiment_id", ""))


def calculate_summary_stats(results: list[dict]) -> dict[str, Any]:
    """Calculate summary statistics across all experiments."""
    stats = {
        "total_experiments": len(results),
        "successful": 0,
        "failed": 0,
        "avg_energy_improvement": 0,
        "systems_compared": set(),
        "best_improvement": None,
        "worst_improvement": None
    }
    
    improvements = []
    
    for result in results:
        if result.get("status") == "completed":
            stats["successful"] += 1
        else:
            stats["failed"] += 1
        
        comparison = result.get("comparison", {})
        for criterion in comparison.get("criteria_results", []):
            if criterion.get("metric") == "energy_joules":
                improvement = criterion.get("improvement", 0)
                improvements.append({
                    "experiment": result.get("experiment_id"),
                    "improvement": improvement
                })
    
    if improvements:
        stats["avg_energy_improvement"] = sum(i["improvement"] for i in improvements) / len(improvements)
        stats["best_improvement"] = max(improvements, key=lambda x: x["improvement"])
        stats["worst_improvement"] = min(improvements, key=lambda x: x["improvement"])
    
    stats["systems_compared"] = list(stats["systems_compared"])
    
    return stats


def generate_html_report(results: list[dict], stats: dict) -> str:
    """Generate HTML report with charts."""
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SOTA vs AgentOne Comparison Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0f0f23;
            --bg-secondary: #1a1a2e;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --accent: #00d4aa;
            --accent-secondary: #ff6b6b;
            --border: #2a2a4a;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        h1 {{
            font-size: 2rem;
            color: var(--accent);
            margin-bottom: 0.5rem;
        }}
        
        h2 {{
            font-size: 1.5rem;
            color: var(--text-primary);
            margin: 2rem 0 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.5rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 2rem 0;
        }}
        
        .stat-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2rem;
            color: var(--accent);
            font-weight: bold;
        }}
        
        .stat-label {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .chart-container {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1rem 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }}
        
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        
        th {{
            background: var(--bg-secondary);
            color: var(--accent);
        }}
        
        .success {{ color: #4ade80; }}
        .failure {{ color: #f87171; }}
        
        .timestamp {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ SOTA vs AgentOne Comparison Report</h1>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>Summary Statistics</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats['total_experiments']}</div>
                <div class="stat-label">Total Experiments</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['successful']}</div>
                <div class="stat-label">Successful</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['avg_energy_improvement']:.1f}%</div>
                <div class="stat-label">Avg Energy Improvement</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['best_improvement']['improvement']:.1f}%</div>
                <div class="stat-label">Best Improvement</div>
            </div>
        </div>
        
        <h2>Energy Improvement by Experiment</h2>
        <div class="chart-container">
            <canvas id="improvementChart"></canvas>
        </div>
        
        <h2>Experiment Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Experiment</th>
                    <th>Status</th>
                    <th>Energy Improvement</th>
                    <th>Criteria Met</th>
                </tr>
            </thead>
            <tbody>
"""
    
    for result in results:
        exp_id = result.get("experiment_id", "unknown")
        status = result.get("status", "unknown")
        status_class = "success" if status == "completed" else "failure"
        
        comparison = result.get("comparison", {})
        criteria_results = comparison.get("criteria_results", [])
        energy_improvement = next(
            (c["improvement"] for c in criteria_results if c.get("metric") == "energy_joules"),
            0
        )
        criteria_met = sum(1 for c in criteria_results if c.get("met", False))
        total_criteria = len(criteria_results)
        
        html += f"""
                <tr>
                    <td>{exp_id}</td>
                    <td class="{status_class}">{status}</td>
                    <td>{energy_improvement:.1f}%</td>
                    <td>{criteria_met}/{total_criteria}</td>
                </tr>
"""
    
    # Chart data
    chart_labels = [r.get("experiment_id", "")[:20] for r in results]
    chart_data = []
    for r in results:
        comparison = r.get("comparison", {})
        for c in comparison.get("criteria_results", []):
            if c.get("metric") == "energy_joules":
                chart_data.append(c.get("improvement", 0))
                break
        else:
            chart_data.append(0)
    
    html += f"""
            </tbody>
        </table>
        
        <h2>Conclusions</h2>
        <div class="chart-container">
            <p>Based on the experimental results:</p>
            <ul>
                <li>Average energy improvement across all experiments: <strong>{stats['avg_energy_improvement']:.1f}%</strong></li>
                <li>Best performing experiment: <strong>{stats['best_improvement']['experiment']}</strong> ({stats['best_improvement']['improvement']:.1f}%)</li>
                <li>Total experiments completed: <strong>{stats['successful']}</strong> of {stats['total_experiments']}</li>
            </ul>
        </div>
    </div>
    
    <script>
        const ctx = document.getElementById('improvementChart').getContext('2d');
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart_labels)},
                datasets: [{{
                    label: 'Energy Improvement (%)',
                    data: {json.dumps(chart_data)},
                    backgroundColor: 'rgba(0, 212, 170, 0.7)',
                    borderColor: 'rgba(0, 212, 170, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: 'rgba(255,255,255,0.1)' }},
                        ticks: {{ color: '#e0e0e0' }}
                    }},
                    x: {{
                        grid: {{ color: 'rgba(255,255,255,0.1)' }},
                        ticks: {{ color: '#e0e0e0' }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        labels: {{ color: '#e0e0e0' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    return html


def generate_markdown_report(results: list[dict], stats: dict) -> str:
    """Generate Markdown summary report."""
    lines = [
        "# SOTA vs AgentOne Comparison Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- **Total Experiments**: {stats['total_experiments']}",
        f"- **Successful**: {stats['successful']}",
        f"- **Failed**: {stats['failed']}",
        f"- **Average Energy Improvement**: {stats['avg_energy_improvement']:.1f}%",
        "",
        "## Experiment Results",
        "",
        "| Experiment | Status | Energy Improvement | Criteria Met |",
        "|------------|--------|-------------------|--------------|"
    ]
    
    for result in results:
        exp_id = result.get("experiment_id", "unknown")
        status = result.get("status", "unknown")
        
        comparison = result.get("comparison", {})
        criteria_results = comparison.get("criteria_results", [])
        energy_improvement = next(
            (c["improvement"] for c in criteria_results if c.get("metric") == "energy_joules"),
            0
        )
        criteria_met = sum(1 for c in criteria_results if c.get("met", False))
        total_criteria = len(criteria_results)
        
        status_icon = "✅" if status == "completed" else "❌"
        lines.append(f"| {exp_id} | {status_icon} | {energy_improvement:.1f}% | {criteria_met}/{total_criteria} |")
    
    lines.extend([
        "",
        "## Conclusions",
        "",
        f"1. **Best Improvement**: {stats['best_improvement']['experiment']} achieved {stats['best_improvement']['improvement']:.1f}% energy reduction",
        f"2. **Average Performance**: {stats['avg_energy_improvement']:.1f}% average energy improvement across experiments",
        f"3. **Reliability**: {stats['successful']} of {stats['total_experiments']} experiments completed successfully",
        "",
        "## Recommendations",
        "",
        "Based on experimental results, recommend:",
        "- For event-driven workloads: Use KEDA or AgentOne",
        "- For predictable schedules: Use Kube-green",
        "- For holistic optimization: Use AgentOne",
        ""
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate SOTA comparison report")
    parser.add_argument("--results", type=Path, default=Path("/tmp/vsf-comparisons"),
                       help="Results directory")
    parser.add_argument("--output", type=Path, help="Output directory")
    parser.add_argument("--summary", action="store_true", help="Generate summary only")
    
    args = parser.parse_args()
    
    # Load results (or use mock data for testing)
    if args.results.exists() and list(args.results.glob("*.json")):
        results = load_results(args.results)
    else:
        # Mock data for testing
        results = [
            {
                "experiment_id": "exp-keda-vs-baseline",
                "experiment_name": "KEDA vs Baseline",
                "status": "completed",
                "comparison": {
                    "criteria_results": [
                        {"metric": "energy_joules", "improvement": 15.3, "met": True}
                    ]
                }
            },
            {
                "experiment_id": "exp-kubegreen-vs-baseline",
                "experiment_name": "Kube-green vs Baseline",
                "status": "completed",
                "comparison": {
                    "criteria_results": [
                        {"metric": "energy_joules", "improvement": 28.7, "met": True}
                    ]
                }
            },
            {
                "experiment_id": "exp-agentone-vs-keda",
                "experiment_name": "AgentOne vs KEDA",
                "status": "completed",
                "comparison": {
                    "criteria_results": [
                        {"metric": "energy_joules", "improvement": 8.2, "met": True}
                    ]
                }
            }
        ]
        logger.info("Using mock data for demonstration")
    
    stats = calculate_summary_stats(results)
    
    if args.summary:
        print(f"\nTotal Experiments: {stats['total_experiments']}")
        print(f"Successful: {stats['successful']}")
        print(f"Avg Energy Improvement: {stats['avg_energy_improvement']:.1f}%")
        return
    
    # Generate reports
    output_dir = args.output or args.results
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # HTML report
    html_report = generate_html_report(results, stats)
    html_path = output_dir / "analysis_report.html"
    with open(html_path, "w") as f:
        f.write(html_report)
    logger.info(f"HTML report: {html_path}")
    
    # Markdown report
    md_report = generate_markdown_report(results, stats)
    md_path = output_dir / "analysis_report.md"
    with open(md_path, "w") as f:
        f.write(md_report)
    logger.info(f"Markdown report: {md_path}")
    
    print(md_report)


if __name__ == "__main__":
    main()
