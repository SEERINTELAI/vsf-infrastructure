#!/usr/bin/env python3
"""
kepler-validation-test.py - Cross-validate Kepler vs Scaphandre power metrics

Run this AFTER both Kepler and Scaphandre are deployed to validate power
measurement accuracy. Compares container-level estimates from Kepler against
host-level measurements from Scaphandre.

Usage:
    python kepler-validation-test.py                    # Run all validations
    python kepler-validation-test.py --prometheus-url   # Custom Prometheus URL
    python kepler-validation-test.py --threshold 0.3    # Custom divergence threshold

Requirements:
    - Prometheus running and accessible
    - Kepler deployed and scraping
    - Scaphandre deployed and scraping
    - requests library (pip install requests)
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    name: str
    passed: bool
    message: str
    value: float | None = None
    threshold: float | None = None


class PrometheusClient:
    """Simple Prometheus query client."""
    
    def __init__(self, url: str = "http://prometheus:9090"):
        self.url = url.rstrip("/")
        self.api_url = f"{self.url}/api/v1"
    
    def query(self, promql: str) -> list[dict[str, Any]]:
        """Execute instant query and return results."""
        try:
            response = requests.get(
                f"{self.api_url}/query",
                params={"query": promql},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data["status"] != "success":
                logger.error(f"Query failed: {data.get('error', 'unknown')}")
                return []
            
            return data["data"]["result"]
        except requests.RequestException as e:
            logger.error(f"Prometheus query failed: {e}")
            return []
    
    def query_range(
        self, 
        promql: str, 
        start: float, 
        end: float, 
        step: str = "15s"
    ) -> list[dict[str, Any]]:
        """Execute range query and return results."""
        try:
            response = requests.get(
                f"{self.api_url}/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": step
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            if data["status"] != "success":
                logger.error(f"Range query failed: {data.get('error', 'unknown')}")
                return []
            
            return data["data"]["result"]
        except requests.RequestException as e:
            logger.error(f"Prometheus range query failed: {e}")
            return []


class KeplerValidator:
    """Validate Kepler power metrics."""
    
    def __init__(self, prom: PrometheusClient):
        self.prom = prom
        self.results: list[ValidationResult] = []
    
    def check_kepler_running(self) -> ValidationResult:
        """Check if Kepler pods are running and scraping."""
        results = self.prom.query('up{job=~".*kepler.*"}')
        
        if not results:
            return ValidationResult(
                name="kepler_running",
                passed=False,
                message="No Kepler targets found in Prometheus"
            )
        
        up_count = sum(1 for r in results if float(r["value"][1]) == 1)
        total = len(results)
        
        if up_count == total:
            return ValidationResult(
                name="kepler_running",
                passed=True,
                message=f"All {total} Kepler targets are UP",
                value=float(up_count)
            )
        else:
            return ValidationResult(
                name="kepler_running",
                passed=False,
                message=f"Only {up_count}/{total} Kepler targets are UP",
                value=float(up_count)
            )
    
    def check_kepler_container_joules(self) -> ValidationResult:
        """Check if Kepler container joules metric exists."""
        results = self.prom.query('count(kepler_container_joules_total)')
        
        if not results:
            return ValidationResult(
                name="kepler_container_joules",
                passed=False,
                message="kepler_container_joules_total metric not found"
            )
        
        count = float(results[0]["value"][1])
        if count > 0:
            return ValidationResult(
                name="kepler_container_joules",
                passed=True,
                message=f"Found {int(count)} container power metrics",
                value=count
            )
        else:
            return ValidationResult(
                name="kepler_container_joules",
                passed=False,
                message="kepler_container_joules_total has no data"
            )
    
    def check_kepler_node_power(self) -> ValidationResult:
        """Check if Kepler is measuring node-level power."""
        results = self.prom.query(
            'sum by (instance) (rate(kepler_container_joules_total[5m]))'
        )
        
        if not results:
            return ValidationResult(
                name="kepler_node_power",
                passed=False,
                message="No node power data from Kepler"
            )
        
        nodes_with_power = 0
        for r in results:
            power = float(r["value"][1])
            if power > 0:
                nodes_with_power += 1
        
        if nodes_with_power > 0:
            return ValidationResult(
                name="kepler_node_power",
                passed=True,
                message=f"{nodes_with_power} nodes reporting power data",
                value=float(nodes_with_power)
            )
        else:
            return ValidationResult(
                name="kepler_node_power",
                passed=False,
                message="Kepler showing zero power on all nodes"
            )


class ScaphandreValidator:
    """Validate Scaphandre power metrics."""
    
    def __init__(self, prom: PrometheusClient):
        self.prom = prom
        self.results: list[ValidationResult] = []
    
    def check_scaphandre_running(self) -> ValidationResult:
        """Check if Scaphandre is running and scraping."""
        results = self.prom.query('up{job=~".*scaphandre.*"}')
        
        if not results:
            return ValidationResult(
                name="scaphandre_running",
                passed=False,
                message="No Scaphandre targets found in Prometheus"
            )
        
        up_count = sum(1 for r in results if float(r["value"][1]) == 1)
        
        if up_count > 0:
            return ValidationResult(
                name="scaphandre_running",
                passed=True,
                message=f"Scaphandre is UP ({up_count} target(s))",
                value=float(up_count)
            )
        else:
            return ValidationResult(
                name="scaphandre_running",
                passed=False,
                message="Scaphandre target(s) are DOWN"
            )
    
    def check_scaphandre_host_power(self) -> ValidationResult:
        """Check if Scaphandre is measuring host power."""
        results = self.prom.query('scaph_host_power_microwatts')
        
        if not results:
            return ValidationResult(
                name="scaphandre_host_power",
                passed=False,
                message="scaph_host_power_microwatts metric not found"
            )
        
        power_uw = float(results[0]["value"][1])
        power_w = power_uw / 1_000_000
        
        if power_w > 0:
            return ValidationResult(
                name="scaphandre_host_power",
                passed=True,
                message=f"Host power: {power_w:.2f}W",
                value=power_w
            )
        else:
            return ValidationResult(
                name="scaphandre_host_power",
                passed=False,
                message="Scaphandre showing zero host power"
            )


class CrossValidator:
    """Cross-validate Kepler vs Scaphandre measurements."""
    
    def __init__(self, prom: PrometheusClient, divergence_threshold: float = 0.3):
        self.prom = prom
        self.divergence_threshold = divergence_threshold
    
    def compare_total_power(self) -> ValidationResult:
        """Compare total power: sum(Kepler containers) vs Scaphandre host."""
        # Get Kepler total (sum of all containers)
        kepler_results = self.prom.query(
            'sum(rate(kepler_container_joules_total[5m]))'
        )
        
        # Get Scaphandre host power in watts
        scaph_results = self.prom.query(
            'scaph_host_power_microwatts / 1000000'
        )
        
        if not kepler_results or not scaph_results:
            return ValidationResult(
                name="power_comparison",
                passed=False,
                message="Cannot compare: missing Kepler or Scaphandre data"
            )
        
        kepler_power = float(kepler_results[0]["value"][1])
        scaph_power = float(scaph_results[0]["value"][1])
        
        if scaph_power == 0:
            return ValidationResult(
                name="power_comparison",
                passed=False,
                message="Scaphandre power is zero - cannot compare"
            )
        
        # Calculate divergence (relative difference)
        divergence = abs(kepler_power - scaph_power) / scaph_power
        
        passed = divergence <= self.divergence_threshold
        
        return ValidationResult(
            name="power_comparison",
            passed=passed,
            message=(
                f"Kepler: {kepler_power:.2f}W, Scaphandre: {scaph_power:.2f}W, "
                f"Divergence: {divergence*100:.1f}% "
                f"({'OK' if passed else 'EXCEEDS'} threshold {self.divergence_threshold*100:.0f}%)"
            ),
            value=divergence,
            threshold=self.divergence_threshold
        )
    
    def check_recording_rules(self) -> ValidationResult:
        """Check if AK recording rules are active."""
        rules_to_check = [
            "ak:node_power_watts",
            "ak:container_power_watts",
        ]
        
        found = []
        missing = []
        
        for rule in rules_to_check:
            results = self.prom.query(f'count({rule})')
            if results and float(results[0]["value"][1]) > 0:
                found.append(rule)
            else:
                missing.append(rule)
        
        if not missing:
            return ValidationResult(
                name="recording_rules",
                passed=True,
                message=f"All AK recording rules active: {', '.join(found)}",
                value=float(len(found))
            )
        else:
            return ValidationResult(
                name="recording_rules",
                passed=False,
                message=f"Missing recording rules: {', '.join(missing)}",
                value=float(len(found))
            )


def run_validation(
    prometheus_url: str,
    divergence_threshold: float
) -> tuple[list[ValidationResult], bool]:
    """Run all validation checks and return results."""
    prom = PrometheusClient(prometheus_url)
    results: list[ValidationResult] = []
    
    # Check Prometheus connectivity
    logger.info("Checking Prometheus connectivity...")
    try:
        test = prom.query('up')
        if not test:
            logger.error("Cannot connect to Prometheus or no targets")
            return [], False
    except Exception as e:
        logger.error(f"Prometheus connection failed: {e}")
        return [], False
    
    logger.info("Running Kepler validations...")
    kepler = KeplerValidator(prom)
    results.append(kepler.check_kepler_running())
    results.append(kepler.check_kepler_container_joules())
    results.append(kepler.check_kepler_node_power())
    
    logger.info("Running Scaphandre validations...")
    scaph = ScaphandreValidator(prom)
    results.append(scaph.check_scaphandre_running())
    results.append(scaph.check_scaphandre_host_power())
    
    logger.info("Running cross-validation...")
    cross = CrossValidator(prom, divergence_threshold)
    results.append(cross.compare_total_power())
    results.append(cross.check_recording_rules())
    
    all_passed = all(r.passed for r in results)
    return results, all_passed


def print_results(results: list[ValidationResult]) -> None:
    """Print validation results in a formatted table."""
    print("\n" + "=" * 70)
    print("KEPLER VALIDATION RESULTS")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"\n{status} | {r.name}")
        print(f"       {r.message}")
        if r.passed:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "-" * 70)
    print(f"Summary: {passed} passed, {failed} failed")
    print("=" * 70)


def save_report(results: list[ValidationResult], output_path: Path) -> None:
    """Save validation report to JSON file."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed)
        },
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "value": r.value,
                "threshold": r.threshold
            }
            for r in results
        ]
    }
    
    output_path.write_text(json.dumps(report, indent=2))
    logger.info(f"Report saved to: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Kepler power metrics against Scaphandre"
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090",
        help="Prometheus server URL (default: http://localhost:9090)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Max divergence threshold between Kepler and Scaphandre (default: 0.3 = 30%%)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON report path"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output"
    )
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    logger.info(f"Validating against Prometheus at {args.prometheus_url}")
    logger.info(f"Divergence threshold: {args.threshold*100:.0f}%")
    
    results, all_passed = run_validation(args.prometheus_url, args.threshold)
    
    if not results:
        print("ERROR: Validation failed - could not collect results")
        return 1
    
    print_results(results)
    
    if args.output:
        save_report(results, args.output)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
