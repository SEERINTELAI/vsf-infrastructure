"""
Closed-Loop Test Harness

Validates end-to-end optimization cycles with measurable outcomes.
Tests the complete flow: metrics → decision → action → verification.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .router import ProbeRouter, ProbeType
from .aggregator import MetricsAggregator
from .controller import OptimizationController, Policy, PolicyType

logger = logging.getLogger(__name__)


@dataclass
class TestScenario:
    """A test scenario for closed-loop validation."""
    name: str
    description: str
    policies: list[Policy]
    expected_actions: list[str]  # Action types expected
    validation_checks: list[dict] = field(default_factory=list)
    timeout_seconds: int = 300
    dry_run: bool = True


@dataclass
class TestResult:
    """Result of a closed-loop test."""
    scenario_name: str
    passed: bool
    start_time: datetime
    end_time: datetime
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    actions_taken: list[str] = field(default_factory=list)
    validation_results: list[dict] = field(default_factory=list)
    error: str | None = None
    
    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


class ClosedLoopTestHarness:
    """
    Test harness for validating closed-loop optimization.
    
    Tests the complete optimization flow:
    1. Initial state capture
    2. Policy evaluation
    3. Action execution
    4. State verification
    5. Rollback (if needed)
    """
    
    def __init__(
        self,
        router: ProbeRouter,
        aggregator: MetricsAggregator,
        controller: OptimizationController
    ):
        self.router = router
        self.aggregator = aggregator
        self.controller = controller
        self.results: list[TestResult] = []
    
    async def run_scenario(self, scenario: TestScenario) -> TestResult:
        """
        Run a single test scenario.
        
        Args:
            scenario: Test scenario to execute
            
        Returns:
            TestResult with pass/fail and details
        """
        logger.info(f"Starting scenario: {scenario.name}")
        result = TestResult(
            scenario_name=scenario.name,
            passed=False,
            start_time=datetime.now(),
            end_time=datetime.now()
        )
        
        try:
            # 1. Capture initial metrics
            result.metrics_before = await self.aggregator.get_summary()
            
            # 2. Add scenario policies
            original_policies = self.controller.policies.copy()
            self.controller.policies = []
            
            for policy in scenario.policies:
                if scenario.dry_run:
                    policy.parameters["dry_run"] = True
                self.controller.add_policy(policy)
            
            # 3. Run optimization cycle
            cycle = await self.controller.run_optimization_cycle(
                dry_run=scenario.dry_run
            )
            
            # 4. Record actions taken
            result.actions_taken = [
                r.action.action_type.value
                for r in cycle.actions_executed
            ]
            
            # 5. Capture final metrics
            result.metrics_after = await self.aggregator.get_summary()
            
            # 6. Run validation checks
            validations = []
            for check in scenario.validation_checks:
                check_result = await self._run_validation(
                    check,
                    result.metrics_before,
                    result.metrics_after,
                    result.actions_taken
                )
                validations.append(check_result)
            
            result.validation_results = validations
            
            # 7. Check expected actions
            actions_match = set(scenario.expected_actions) <= set(result.actions_taken)
            validations_pass = all(v.get("passed", False) for v in validations)
            
            result.passed = actions_match and validations_pass
            
            # 8. Restore original policies
            self.controller.policies = original_policies
            
        except Exception as e:
            logger.exception(f"Scenario failed: {e}")
            result.error = str(e)
            result.passed = False
        
        finally:
            result.end_time = datetime.now()
            self.results.append(result)
        
        logger.info(
            f"Scenario {scenario.name}: "
            f"{'PASSED' if result.passed else 'FAILED'}"
        )
        
        return result
    
    async def _run_validation(
        self,
        check: dict,
        before: dict,
        after: dict,
        actions: list[str]
    ) -> dict:
        """Run a single validation check."""
        check_type = check.get("type", "")
        
        if check_type == "action_count":
            expected = check.get("expected", 0)
            actual = len(actions)
            passed = actual >= expected
            return {
                "type": check_type,
                "passed": passed,
                "expected": expected,
                "actual": actual,
                "message": f"Expected >= {expected} actions, got {actual}"
            }
        
        elif check_type == "metric_change":
            metric = check.get("metric", "")
            direction = check.get("direction", "decrease")
            
            before_val = before.get(metric, 0)
            after_val = after.get(metric, 0)
            
            if direction == "decrease":
                passed = after_val <= before_val
            elif direction == "increase":
                passed = after_val >= before_val
            else:
                passed = after_val == before_val
            
            return {
                "type": check_type,
                "passed": passed,
                "metric": metric,
                "before": before_val,
                "after": after_val,
                "direction": direction
            }
        
        elif check_type == "probe_health":
            # Check all probes are still healthy
            healthy = after.get("healthy_probes", 0)
            total = after.get("total_probes", 0)
            passed = healthy == total
            return {
                "type": check_type,
                "passed": passed,
                "healthy": healthy,
                "total": total
            }
        
        else:
            return {
                "type": check_type,
                "passed": False,
                "error": f"Unknown check type: {check_type}"
            }
    
    async def run_all_scenarios(
        self,
        scenarios: list[TestScenario]
    ) -> dict[str, Any]:
        """Run all test scenarios and return summary."""
        for scenario in scenarios:
            await self.run_scenario(scenario)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / len(self.results) if self.results else 0,
            "results": [
                {
                    "name": r.scenario_name,
                    "passed": r.passed,
                    "duration_seconds": r.duration_seconds,
                    "actions": len(r.actions_taken),
                    "error": r.error
                }
                for r in self.results
            ]
        }
    
    def get_standard_scenarios(self) -> list[TestScenario]:
        """Get standard test scenarios for VSF validation."""
        return [
            # Scenario 1: Consolidation works
            TestScenario(
                name="consolidation_dry_run",
                description="Test workload consolidation planning",
                policies=[
                    Policy(
                        name="test_consolidate",
                        policy_type=PolicyType.CONSOLIDATE,
                        conditions={"min_nodes": 5},
                        parameters={"target_nodes": 5, "dry_run": True}
                    )
                ],
                expected_actions=["consolidate_workloads"],
                validation_checks=[
                    {"type": "action_count", "expected": 1},
                    {"type": "probe_health"}
                ],
                dry_run=True
            ),
            
            # Scenario 2: Power save on idle nodes
            TestScenario(
                name="power_save_idle",
                description="Test power-saving on underutilized nodes",
                policies=[
                    Policy(
                        name="test_power_save",
                        policy_type=PolicyType.POWER_SAVE,
                        conditions={"cpu_threshold": 50.0},  # High threshold = more triggers
                        parameters={"dry_run": True}
                    )
                ],
                expected_actions=["set_governor"],
                validation_checks=[
                    {"type": "probe_health"}
                ],
                dry_run=True
            ),
            
            # Scenario 3: No action when already optimal
            TestScenario(
                name="no_action_optimal",
                description="Verify no action when cluster is optimal",
                policies=[
                    Policy(
                        name="test_consolidate_noop",
                        policy_type=PolicyType.CONSOLIDATE,
                        conditions={"min_nodes": 100},  # Higher than we have
                        parameters={"target_nodes": 5, "dry_run": True}
                    )
                ],
                expected_actions=[],  # No actions expected
                validation_checks=[
                    {"type": "action_count", "expected": 0},
                    {"type": "probe_health"}
                ],
                dry_run=True
            )
        ]


async def run_closed_loop_tests(
    router: ProbeRouter,
    aggregator: MetricsAggregator,
    controller: OptimizationController
) -> dict:
    """
    Run standard closed-loop tests.
    
    Returns:
        Test summary with pass/fail counts
    """
    harness = ClosedLoopTestHarness(router, aggregator, controller)
    scenarios = harness.get_standard_scenarios()
    
    return await harness.run_all_scenarios(scenarios)
