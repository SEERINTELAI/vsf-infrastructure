#!/usr/bin/env python3
"""
Closed-Loop Optimization Test

Validates end-to-end optimization flow:
1. Collect metrics from all 23 probes
2. Evaluate consolidation policy
3. Execute optimization (dry-run by default)
4. Verify outcomes

Usage:
    python scripts/run_closed_loop_test.py
    python scripts/run_closed_loop_test.py --live  # Actually execute (dangerous!)
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from optimization.router import ProbeRouter, ProbeType
from optimization.aggregator import MetricsAggregator
from optimization.controller import OptimizationController, Policy, PolicyType
from optimization.test_harness import ClosedLoopTestHarness, run_closed_loop_tests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def create_mock_router() -> ProbeRouter:
    """Create router with mock probes for testing."""
    router = ProbeRouter()
    
    # K8s Probe
    router.register_probe(
        probe_id="k8s-probe",
        probe_type=ProbeType.K8S,
        endpoint="http://k8s-probe.vsf.local:8080/mcp",
        hostname="vsf-cluster"
    )
    
    # Control Plane VMs
    for i in range(1, 4):
        router.register_probe(
            probe_id=f"vsf-cp-{i}",
            probe_type=ProbeType.VM_SYSTEM,
            endpoint=f"http://vsf-cp-{i}.vsf.local:8765/mcp",
            hostname=f"vsf-cp-{i}"
        )
    
    # Worker VMs
    for i in range(1, 11):
        router.register_probe(
            probe_id=f"vsf-worker-{i}",
            probe_type=ProbeType.VM_SYSTEM,
            endpoint=f"http://vsf-worker-{i}.vsf.local:8765/mcp",
            hostname=f"vsf-worker-{i}"
        )
    
    # GPU Worker VMs
    for i in range(1, 9):
        router.register_probe(
            probe_id=f"vsf-gpu-{i}",
            probe_type=ProbeType.VM_SYSTEM,
            endpoint=f"http://vsf-gpu-{i}.vsf.local:8765/mcp",
            hostname=f"vsf-gpu-{i}"
        )
    
    # Host System Probe (Bizon1)
    router.register_probe(
        probe_id="bizon1",
        probe_type=ProbeType.HOST_SYSTEM,
        endpoint="http://bizon1.local:8765/mcp",
        hostname="bizon1"
    )
    
    return router


async def run_tests(dry_run: bool = True) -> dict:
    """Run closed-loop optimization tests."""
    
    print("=" * 60)
    print("VSF CLOSED-LOOP OPTIMIZATION TEST")
    print("=" * 60)
    print(f"Mode: {'DRY RUN (safe)' if dry_run else 'LIVE (executing actions!)'}")
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    # Create components
    router = create_mock_router()
    aggregator = MetricsAggregator(router)
    controller = OptimizationController(router, aggregator)
    
    # Add test policies
    controller.add_policy(Policy(
        name="consolidation_test",
        policy_type=PolicyType.CONSOLIDATE,
        priority=10,
        conditions={"min_nodes": 10},
        parameters={
            "target_nodes": 5,
            "dry_run": dry_run
        }
    ))
    
    controller.add_policy(Policy(
        name="power_save_test",
        policy_type=PolicyType.POWER_SAVE,
        priority=5,
        conditions={"cpu_threshold": 30.0},
        parameters={"dry_run": dry_run}
    ))
    
    print("Registered Probes:")
    for probe in router.list_probes():
        print(f"  • {probe.probe_id} ({probe.probe_type.value}) - {probe.endpoint}")
    print()
    
    print("Active Policies:")
    for policy in controller.policies:
        print(f"  • {policy.name} ({policy.policy_type.value}) - priority {policy.priority}")
    print()
    
    # Run test harness
    print("Running test scenarios...")
    print("-" * 40)
    
    harness = ClosedLoopTestHarness(router, aggregator, controller)
    scenarios = harness.get_standard_scenarios()
    
    # Force dry_run for all scenarios
    for scenario in scenarios:
        scenario.dry_run = dry_run
    
    results = await harness.run_all_scenarios(scenarios)
    
    # Print results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total Scenarios: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Pass Rate: {results['pass_rate']*100:.1f}%")
    print()
    
    print("Scenario Details:")
    for r in results['results']:
        status = "✅ PASS" if r['passed'] else "❌ FAIL"
        print(f"  {status} {r['name']}")
        print(f"       Duration: {r['duration_seconds']:.2f}s, Actions: {r['actions']}")
        if r['error']:
            print(f"       Error: {r['error']}")
    print()
    
    # Run a full optimization cycle
    print("=" * 60)
    print("OPTIMIZATION CYCLE TEST")
    print("=" * 60)
    
    cycle = await controller.run_optimization_cycle(dry_run=dry_run)
    summary = controller.get_cycle_summary(cycle)
    
    print(f"Cycle ID: {summary['cycle_id']}")
    print(f"Success: {summary['success']}")
    print(f"Duration: {summary['duration_seconds']}s")
    print(f"Policies Evaluated: {summary['policies_evaluated']}")
    print(f"Actions Planned: {summary['actions_planned']}")
    print(f"Actions Executed: {summary['actions_executed']}")
    print(f"  Succeeded: {summary['actions_succeeded']}")
    print(f"  Failed: {summary['actions_failed']}")
    
    if summary['error']:
        print(f"Error: {summary['error']}")
    
    print()
    
    # Cleanup
    await router.close()
    
    # Overall result
    overall_success = results['failed'] == 0 and summary['success']
    
    print("=" * 60)
    if overall_success:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    
    return {
        "test_results": results,
        "optimization_cycle": summary,
        "overall_success": overall_success
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run VSF closed-loop optimization tests"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute actions for real (dangerous!)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Write results to JSON file"
    )
    
    args = parser.parse_args()
    
    if args.live:
        print("⚠️  WARNING: Running in LIVE mode!")
        print("    Actions will be executed for real.")
        response = input("    Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    
    results = asyncio.run(run_tests(dry_run=not args.live))
    
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results written to: {output_path}")
    
    sys.exit(0 if results['overall_success'] else 1)


if __name__ == "__main__":
    main()
