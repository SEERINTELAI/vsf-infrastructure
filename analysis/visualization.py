"""
Chart Generator

Generates visualizations for experiment data.
Uses HTML/CSS for portable output.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Generates charts as HTML files.
    
    Uses Chart.js for visualization (no backend dependencies).
    """
    
    HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .chart-container {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        h1 {{
            color: #e94560;
        }}
        h2 {{
            color: #0f3460;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #0f3460;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #e94560;
        }}
        .metric-label {{
            color: #aaa;
            margin-top: 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        {content}
    </div>
    <script>
        {script}
    </script>
</body>
</html>'''
    
    def __init__(self, output_dir: str | Path = "/tmp/vsf-charts"):
        self.output_dir = Path(output_dir)
    
    def _ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir
    
    def _generate_chart_config(
        self,
        chart_type: str,
        labels: list[str],
        datasets: list[dict],
        options: dict | None = None
    ) -> str:
        """Generate Chart.js configuration."""
        config = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "options": options or {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "top"}
                }
            }
        }
        return json.dumps(config)
    
    def generate_timeseries_chart(
        self,
        phases: list[dict],
        metric: str,
        title: str = "Power Over Time"
    ) -> str:
        """
        Generate timeseries chart HTML.
        
        Args:
            phases: List of phase data with metrics
            metric: Metric to plot
            title: Chart title
            
        Returns:
            HTML string
        """
        datasets = []
        colors = ["#e94560", "#0f3460", "#1a1a2e", "#f9a826"]
        
        for i, phase in enumerate(phases):
            metrics = phase.get("metrics", [])
            if not metrics:
                continue
            
            values = [m.get(metric, 0) for m in metrics]
            labels = [m.get("timestamp", str(j)) for j, m in enumerate(metrics)]
            
            datasets.append({
                "label": phase.get("name", f"Phase {i+1}"),
                "data": values,
                "borderColor": colors[i % len(colors)],
                "tension": 0.1,
                "fill": False
            })
        
        if not datasets:
            return "<p>No data to display</p>"
        
        # Use first phase labels
        all_labels = []
        for phase in phases:
            for m in phase.get("metrics", []):
                ts = m.get("timestamp", "")
                if ts and ts not in all_labels:
                    all_labels.append(ts)
        
        config = self._generate_chart_config(
            "line",
            all_labels[:50],  # Limit labels
            datasets,
            {
                "responsive": True,
                "scales": {
                    "y": {
                        "title": {"display": True, "text": metric}
                    }
                }
            }
        )
        
        content = f'''
        <div class="chart-container">
            <canvas id="timeseriesChart"></canvas>
        </div>
        '''
        
        script = f'''
        const ctx = document.getElementById('timeseriesChart').getContext('2d');
        new Chart(ctx, {config});
        '''
        
        return self.HTML_TEMPLATE.format(title=title, content=content, script=script)
    
    def generate_comparison_chart(
        self,
        comparisons: list[dict],
        metric: str = "power_watts"
    ) -> str:
        """
        Generate bar chart comparing baseline vs optimized.
        
        Args:
            comparisons: Comparison data from report summary
            metric: Metric to display
            
        Returns:
            HTML string
        """
        labels = []
        baseline_data = []
        optimized_data = []
        
        for comp in comparisons:
            labels.append(comp.get("phase", "Unknown"))
            metrics = comp.get("metrics", {}).get(metric, {})
            baseline_data.append(metrics.get("baseline_mean", 0))
            optimized_data.append(metrics.get("optimized_mean", 0))
        
        # Add baseline reference
        labels.insert(0, "Baseline")
        baseline_data.insert(0, baseline_data[0] if baseline_data else 0)
        optimized_data.insert(0, baseline_data[0] if baseline_data else 0)
        
        datasets = [
            {
                "label": "Baseline",
                "data": baseline_data,
                "backgroundColor": "#e94560"
            },
            {
                "label": "Optimized",
                "data": optimized_data,
                "backgroundColor": "#0f3460"
            }
        ]
        
        config = self._generate_chart_config(
            "bar",
            labels,
            datasets,
            {
                "responsive": True,
                "scales": {
                    "y": {
                        "title": {"display": True, "text": metric}
                    }
                }
            }
        )
        
        content = f'''
        <div class="chart-container">
            <canvas id="comparisonChart"></canvas>
        </div>
        '''
        
        script = f'''
        const ctx = document.getElementById('comparisonChart').getContext('2d');
        new Chart(ctx, {config});
        '''
        
        return self.HTML_TEMPLATE.format(
            title=f"Comparison: {metric}",
            content=content,
            script=script
        )
    
    def generate_dashboard(
        self,
        experiment_result: dict,
        summary: dict
    ) -> str:
        """
        Generate full dashboard HTML.
        
        Args:
            experiment_result: Full experiment result
            summary: Summary statistics
            
        Returns:
            HTML string
        """
        # Summary cards
        cards = []
        
        for comp in summary.get("comparisons", []):
            for metric, data in comp.get("metrics", {}).items():
                improvement = data.get("improvement_percent", 0)
                direction = "↓" if improvement > 0 else "↑"
                cards.append(f'''
                <div class="metric-card">
                    <div class="metric-value">{abs(improvement):.1f}% {direction}</div>
                    <div class="metric-label">{metric}</div>
                </div>
                ''')
        
        content = f'''
        <div class="summary">
            {"".join(cards[:6])}
        </div>
        <div class="chart-container">
            <canvas id="powerChart"></canvas>
        </div>
        <div class="chart-container">
            <canvas id="cpuChart"></canvas>
        </div>
        '''
        
        # Build chart data from phases
        phases = experiment_result.get("phases", [])
        power_datasets = []
        cpu_datasets = []
        labels = []
        
        colors = ["rgba(233, 69, 96, 0.8)", "rgba(15, 52, 96, 0.8)"]
        
        for i, phase in enumerate(phases):
            metrics = phase.get("metrics", [])
            power_vals = [m.get("power_watts", 0) for m in metrics]
            cpu_vals = [m.get("cpu_percent", 0) for m in metrics]
            
            if not labels:
                labels = list(range(len(power_vals)))
            
            power_datasets.append({
                "label": phase.get("name"),
                "data": power_vals,
                "borderColor": colors[i % 2],
                "tension": 0.1,
                "fill": False
            })
            
            cpu_datasets.append({
                "label": phase.get("name"),
                "data": cpu_vals,
                "borderColor": colors[i % 2],
                "tension": 0.1,
                "fill": False
            })
        
        power_config = json.dumps({
            "type": "line",
            "data": {"labels": labels, "datasets": power_datasets},
            "options": {"responsive": True, "plugins": {"title": {"display": True, "text": "Power (Watts)"}}}
        })
        
        cpu_config = json.dumps({
            "type": "line",
            "data": {"labels": labels, "datasets": cpu_datasets},
            "options": {"responsive": True, "plugins": {"title": {"display": True, "text": "CPU %"}}}
        })
        
        script = f'''
        new Chart(document.getElementById('powerChart'), {power_config});
        new Chart(document.getElementById('cpuChart'), {cpu_config});
        '''
        
        return self.HTML_TEMPLATE.format(
            title=f"Dashboard: {experiment_result.get('experiment_name')}",
            content=content,
            script=script
        )
    
    def save_chart(self, html: str, filename: str) -> Path:
        """Save chart HTML to file."""
        output_dir = self._ensure_output_dir()
        output_path = output_dir / filename
        
        with open(output_path, "w") as f:
            f.write(html)
        
        logger.info(f"Saved chart: {output_path}")
        return output_path
