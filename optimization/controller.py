"""
Optimization Controller

Makes optimization decisions based on policies and metrics.
Coordinates actions across all probes to optimize energy efficiency.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .router import ProbeRouter, ProbeType
from .aggregator import MetricsAggregator, AggregatedMetrics

logger = logging.getLogger(__name__)


class PolicyType(str, Enum):
    """Types of optimization policies."""
    CONSOLIDATE = "consolidate"
    SCALE_DOWN = "scale_down"
    POWER_SAVE = "power_save"
    PERFORMANCE = "performance"


class ActionType(str, Enum):
    """Types of optimization actions."""
    CONSOLIDATE_WORKLOADS = "consolidate_workloads"
    DRAIN_NODE = "drain_node"
    SET_GOVERNOR = "set_governor"
    SET_POWER_CAP = "set_power_cap"
    CORDON_NODE = "cordon_node"
    UNCORDON_NODE = "uncordon_node"


@dataclass
class Policy:
    """Optimization policy definition."""
    name: str
    policy_type: PolicyType
    enabled: bool = True
    priority: int = 0  # Higher = more important
    conditions: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """Planned optimization action."""
    action_type: ActionType
    target: str  # Probe ID or "cluster"
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    policy: str = ""  # Source policy name
    priority: int = 0
    dry_run: bool = False


@dataclass
class ActionResult:
    """Result of executing an action."""
    action: Action
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizationCycle:
    """Record of a complete optimization cycle."""
    cycle_id: str
    start_time: datetime
    end_time: datetime | None = None
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    policies_evaluated: list[str] = field(default_factory=list)
    actions_planned: list[Action] = field(default_factory=list)
    actions_executed: list[ActionResult] = field(default_factory=list)
    success: bool = False
    error: str | None = None


class OptimizationController:
    """
    Coordinates optimization across all VSF probes.
    
    Responsibilities:
    - Evaluate policies against current metrics
    - Plan optimization actions
    - Execute actions in correct order
    - Track and rollback if needed
    - Report results
    """
    
    def __init__(
        self,
        router: ProbeRouter,
        aggregator: MetricsAggregator
    ):
        self.router = router
        self.aggregator = aggregator
        self.policies: list[Policy] = []
        self.history: list[OptimizationCycle] = []
        self._cycle_count = 0
    
    def add_policy(self, policy: Policy):
        """Add an optimization policy."""
        self.policies.append(policy)
        # Sort by priority (higher first)
        self.policies.sort(key=lambda p: p.priority, reverse=True)
        logger.info(f"Added policy: {policy.name} (priority={policy.priority})")
    
    def remove_policy(self, name: str):
        """Remove a policy by name."""
        self.policies = [p for p in self.policies if p.name != name]
    
    def enable_policy(self, name: str, enabled: bool = True):
        """Enable or disable a policy."""
        for policy in self.policies:
            if policy.name == name:
                policy.enabled = enabled
                break
    
    async def evaluate_policies(
        self,
        metrics: AggregatedMetrics
    ) -> list[Action]:
        """
        Evaluate all policies and return planned actions.
        
        Args:
            metrics: Current aggregated metrics
            
        Returns:
            List of planned actions
        """
        actions = []
        
        for policy in self.policies:
            if not policy.enabled:
                continue
            
            policy_actions = await self._evaluate_policy(policy, metrics)
            actions.extend(policy_actions)
        
        # Sort by priority
        actions.sort(key=lambda a: a.priority, reverse=True)
        
        return actions
    
    async def _evaluate_policy(
        self,
        policy: Policy,
        metrics: AggregatedMetrics
    ) -> list[Action]:
        """Evaluate a single policy."""
        actions = []
        
        if policy.policy_type == PolicyType.CONSOLIDATE:
            # Check if consolidation is needed
            if metrics.cluster:
                active_nodes = metrics.cluster.ready_nodes
                target_nodes = policy.parameters.get("target_nodes", 5)
                min_nodes = policy.conditions.get("min_nodes", 10)
                
                if active_nodes > min_nodes:
                    actions.append(Action(
                        action_type=ActionType.CONSOLIDATE_WORKLOADS,
                        target="cluster",
                        parameters={
                            "target_node_count": target_nodes,
                            "dry_run": policy.parameters.get("dry_run", True)
                        },
                        reason=f"Over-provisioned: {active_nodes} > {min_nodes} nodes",
                        policy=policy.name,
                        priority=policy.priority,
                        dry_run=policy.parameters.get("dry_run", True)
                    ))
        
        elif policy.policy_type == PolicyType.POWER_SAVE:
            # Set power-saving governors on underutilized nodes
            threshold = policy.conditions.get("cpu_threshold", 20.0)
            
            for node in metrics.nodes:
                if node.error is None and node.cpu_percent < threshold:
                    actions.append(Action(
                        action_type=ActionType.SET_GOVERNOR,
                        target=node.probe_id,
                        parameters={"governor": "powersave"},
                        reason=f"Low CPU usage: {node.cpu_percent:.1f}%",
                        policy=policy.name,
                        priority=policy.priority,
                        dry_run=policy.parameters.get("dry_run", True)
                    ))
        
        elif policy.policy_type == PolicyType.PERFORMANCE:
            # Set performance governors on high-utilization nodes
            threshold = policy.conditions.get("cpu_threshold", 80.0)
            
            for node in metrics.nodes:
                if node.error is None and node.cpu_percent > threshold:
                    actions.append(Action(
                        action_type=ActionType.SET_GOVERNOR,
                        target=node.probe_id,
                        parameters={"governor": "performance"},
                        reason=f"High CPU usage: {node.cpu_percent:.1f}%",
                        policy=policy.name,
                        priority=policy.priority,
                        dry_run=policy.parameters.get("dry_run", True)
                    ))
        
        return actions
    
    async def execute_action(self, action: Action) -> ActionResult:
        """Execute a single optimization action."""
        import time
        start = time.time()
        
        logger.info(
            f"Executing action: {action.action_type.value} "
            f"on {action.target} (dry_run={action.dry_run})"
        )
        
        try:
            if action.action_type == ActionType.CONSOLIDATE_WORKLOADS:
                result = await self._execute_consolidate(action)
            
            elif action.action_type == ActionType.SET_GOVERNOR:
                result = await self._execute_set_governor(action)
            
            elif action.action_type == ActionType.DRAIN_NODE:
                result = await self._execute_drain_node(action)
            
            elif action.action_type in [ActionType.CORDON_NODE, ActionType.UNCORDON_NODE]:
                result = await self._execute_schedulable(action)
            
            else:
                result = {"error": f"Unknown action type: {action.action_type}"}
            
            duration = (time.time() - start) * 1000
            success = "error" not in result
            
            return ActionResult(
                action=action,
                success=success,
                result=result,
                error=result.get("error") if not success else None,
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.exception(f"Action failed: {e}")
            
            return ActionResult(
                action=action,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    async def _execute_consolidate(self, action: Action) -> dict:
        """Execute workload consolidation via K8s probe."""
        k8s_probes = self.router.list_probes(probe_type=ProbeType.K8S)
        if not k8s_probes:
            return {"error": "No K8s probe available"}
        
        call_result = await self.router.call_tool(
            k8s_probes[0].probe_id,
            "consolidate_workloads",
            action.parameters
        )
        
        if call_result.success:
            return call_result.result or {}
        else:
            return {"error": call_result.error}
    
    async def _execute_set_governor(self, action: Action) -> dict:
        """Execute CPU governor change on target probe."""
        call_result = await self.router.call_tool(
            action.target,
            "set_cpu_governor",
            action.parameters
        )
        
        if call_result.success:
            return call_result.result or {}
        else:
            return {"error": call_result.error}
    
    async def _execute_drain_node(self, action: Action) -> dict:
        """Execute node drain via K8s probe."""
        k8s_probes = self.router.list_probes(probe_type=ProbeType.K8S)
        if not k8s_probes:
            return {"error": "No K8s probe available"}
        
        call_result = await self.router.call_tool(
            k8s_probes[0].probe_id,
            "drain_node",
            {"node_name": action.target, **action.parameters}
        )
        
        if call_result.success:
            return call_result.result or {}
        else:
            return {"error": call_result.error}
    
    async def _execute_schedulable(self, action: Action) -> dict:
        """Execute cordon/uncordon via K8s probe."""
        k8s_probes = self.router.list_probes(probe_type=ProbeType.K8S)
        if not k8s_probes:
            return {"error": "No K8s probe available"}
        
        schedulable = action.action_type == ActionType.UNCORDON_NODE
        
        call_result = await self.router.call_tool(
            k8s_probes[0].probe_id,
            "set_node_schedulable",
            {"node_name": action.target, "schedulable": schedulable}
        )
        
        if call_result.success:
            return call_result.result or {}
        else:
            return {"error": call_result.error}
    
    async def run_optimization_cycle(
        self,
        dry_run: bool = True
    ) -> OptimizationCycle:
        """
        Run a complete optimization cycle.
        
        Steps:
        1. Collect current metrics
        2. Evaluate policies
        3. Plan actions
        4. Execute actions (if not dry_run)
        5. Collect post-metrics
        6. Record results
        
        Args:
            dry_run: If True, plan but don't execute (default True)
            
        Returns:
            OptimizationCycle record
        """
        import uuid
        
        self._cycle_count += 1
        cycle = OptimizationCycle(
            cycle_id=str(uuid.uuid4())[:8],
            start_time=datetime.now()
        )
        
        try:
            # 1. Collect metrics
            logger.info(f"Starting optimization cycle {cycle.cycle_id}")
            metrics = await self.aggregator.collect_all(force_refresh=True)
            cycle.metrics_before = await self.aggregator.get_summary()
            
            # 2. Evaluate policies
            cycle.policies_evaluated = [p.name for p in self.policies if p.enabled]
            
            # 3. Plan actions
            actions = await self.evaluate_policies(metrics)
            
            # Override dry_run if specified
            if dry_run:
                for action in actions:
                    action.dry_run = True
            
            cycle.actions_planned = actions
            
            logger.info(f"Planned {len(actions)} actions")
            
            # 4. Execute actions
            for action in actions:
                result = await self.execute_action(action)
                cycle.actions_executed.append(result)
            
            # 5. Collect post-metrics
            await asyncio.sleep(1)  # Brief pause for effects
            cycle.metrics_after = await self.aggregator.get_summary()
            
            # 6. Record success
            cycle.success = all(r.success for r in cycle.actions_executed)
            
        except Exception as e:
            logger.exception(f"Optimization cycle failed: {e}")
            cycle.success = False
            cycle.error = str(e)
        
        finally:
            cycle.end_time = datetime.now()
            self.history.append(cycle)
        
        return cycle
    
    def get_cycle_summary(self, cycle: OptimizationCycle) -> dict:
        """Get a summary of an optimization cycle."""
        duration = (
            (cycle.end_time - cycle.start_time).total_seconds()
            if cycle.end_time else 0
        )
        
        return {
            "cycle_id": cycle.cycle_id,
            "success": cycle.success,
            "duration_seconds": round(duration, 2),
            "policies_evaluated": len(cycle.policies_evaluated),
            "actions_planned": len(cycle.actions_planned),
            "actions_executed": len(cycle.actions_executed),
            "actions_succeeded": sum(1 for r in cycle.actions_executed if r.success),
            "actions_failed": sum(1 for r in cycle.actions_executed if not r.success),
            "error": cycle.error
        }
