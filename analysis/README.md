# VSF Analysis & Reporting

Statistical analysis and report generation for experiment results.

## Quick Start

```python
from analysis import StatisticalAnalyzer, ReportGenerator, ChartGenerator

# Analyze experiment
analyzer = StatisticalAnalyzer()

# Descriptive stats
stats = analyzer.describe(power_samples)
print(f"Mean: {stats.mean}, Std: {stats.std}")

# Confidence interval
ci = analyzer.confidence_interval(power_samples, confidence=0.95)
print(f"95% CI: [{ci.lower:.2f}, {ci.upper:.2f}]")

# Percent improvement
improvement, ci = analyzer.percent_improvement(baseline, optimized)
print(f"Improvement: {improvement:.1f}% [{ci.lower:.1f}%, {ci.upper:.1f}%]")

# Generate reports
reporter = ReportGenerator(output_dir="/tmp/reports")
summary = reporter.generate_summary(experiment_result)
reporter.save_markdown_report(experiment_result)

# Generate charts
charter = ChartGenerator(output_dir="/tmp/charts")
html = charter.generate_dashboard(experiment_result, summary)
charter.save_chart(html, "dashboard.html")
```

## Statistical Analyzer

### Descriptive Statistics

```python
from analysis import StatisticalAnalyzer

analyzer = StatisticalAnalyzer()
stats = analyzer.describe([100, 105, 98, 102, 104])

print(f"Count: {stats.count}")
print(f"Mean: {stats.mean}")
print(f"Median: {stats.median}")
print(f"Std: {stats.std}")
print(f"Min: {stats.min}, Max: {stats.max}")
```

### Confidence Intervals

```python
# 95% confidence interval
ci = analyzer.confidence_interval(samples, confidence=0.95)
print(f"Mean: {ci.mean}")
print(f"95% CI: [{ci.lower}, {ci.upper}]")
print(f"Margin: ±{ci.margin}")

# Check if value is within CI
if ci.contains(100):
    print("100 is within the CI")
```

### Effect Size

```python
# Cohen's d
d = analyzer.effect_size_cohens_d(baseline, optimized)
interpretation = analyzer.interpret_effect_size(d)
print(f"Effect size: {d:.2f} ({interpretation})")
```

## Report Generator

### JSON Export

```python
reporter = ReportGenerator(output_dir="/tmp/reports")
path = reporter.export_json(experiment_result)
print(f"Exported: {path}")
```

### CSV Export

```python
path = reporter.export_csv(
    metrics=experiment_result["phases"][0]["metrics"],
    filename="baseline_metrics.csv",
    fields=["timestamp", "power_watts", "cpu_percent"]
)
```

### Markdown Report

```python
# Generate and save
path = reporter.save_markdown_report(experiment_result)

# Or get markdown string
summary = reporter.generate_summary(experiment_result)
markdown = reporter.generate_markdown_report(experiment_result, summary)
```

## Chart Generator

### Timeseries Chart

```python
charter = ChartGenerator(output_dir="/tmp/charts")

html = charter.generate_timeseries_chart(
    phases=experiment_result["phases"],
    metric="power_watts",
    title="Power Consumption Over Time"
)
charter.save_chart(html, "power_timeseries.html")
```

### Comparison Chart

```python
html = charter.generate_comparison_chart(
    comparisons=summary["comparisons"],
    metric="power_watts"
)
charter.save_chart(html, "power_comparison.html")
```

### Full Dashboard

```python
html = charter.generate_dashboard(experiment_result, summary)
path = charter.save_chart(html, "dashboard.html")

# Open in browser
import webbrowser
webbrowser.open(f"file://{path}")
```

## Components

### StatisticalAnalyzer

- `describe(samples)` - Descriptive statistics
- `confidence_interval(samples, confidence)` - Calculate CI
- `percent_improvement(baseline, optimized)` - Improvement with CI
- `aggregate_results(results, metric)` - Multi-experiment aggregation
- `effect_size_cohens_d(baseline, optimized)` - Effect size

### ReportGenerator

- `export_json(result)` - JSON export
- `export_csv(metrics, filename)` - CSV export
- `generate_summary(result)` - Summary statistics
- `generate_markdown_report(result)` - Markdown report
- `save_markdown_report(result)` - Save to file

### ChartGenerator

- `generate_timeseries_chart(phases, metric)` - Line chart
- `generate_comparison_chart(comparisons, metric)` - Bar chart
- `generate_dashboard(result, summary)` - Full dashboard
- `save_chart(html, filename)` - Save to file

## Files

- `__init__.py` - Package exports
- `statistics.py` - Statistical analysis functions
- `reports.py` - Report generation
- `visualization.py` - Chart generation
- `README.md` - This file
