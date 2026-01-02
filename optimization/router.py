"""
Multi-Probe Router

Routes MCP commands to the appropriate probe based on target.
Supports 23 probes:
- 1 K8s Probe (cluster-level)
- 21 VM System Probes (per-VM)
- 1 Host System Probe (Bizon1)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ProbeType(str, Enum):
    """Types of probes in the VSF."""
    K8S = "k8s"
    VM_SYSTEM = "vm_system"
    HOST_SYSTEM = "host_system"


@dataclass
class ProbeInfo:
    """Information about a registered probe."""
    probe_id: str
    probe_type: ProbeType
    endpoint: str
    hostname: str
    healthy: bool = True
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if probe hasn't sent heartbeat recently."""
        age = (datetime.now() - self.last_heartbeat).total_seconds()
        return age > timeout_seconds


class MCPCallResult(BaseModel):
    """Result of an MCP tool call."""
    success: bool
    probe_id: str
    tool_name: str
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0


class ProbeRouter:
    """
    Routes MCP commands to appropriate probes.
    
    Responsibilities:
    - Maintain registry of all probes
    - Route commands based on target
    - Handle probe health/availability
    - Retry failed calls
    """
    
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_retries: int = 3
    ):
        self.probes: dict[str, ProbeInfo] = {}
        self.routing_table: dict[str, str] = {}  # target_alias -> probe_id
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self._http_client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client
    
    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    def register_probe(
        self,
        probe_id: str,
        probe_type: ProbeType,
        endpoint: str,
        hostname: str,
        metadata: dict[str, Any] | None = None
    ) -> ProbeInfo:
        """Register a probe with the router."""
        probe = ProbeInfo(
            probe_id=probe_id,
            probe_type=probe_type,
            endpoint=endpoint,
            hostname=hostname,
            metadata=metadata or {}
        )
        self.probes[probe_id] = probe
        
        # Add hostname alias
        self.routing_table[hostname] = probe_id
        
        logger.info(f"Registered probe: {probe_id} ({probe_type}) at {endpoint}")
        return probe
    
    def unregister_probe(self, probe_id: str):
        """Remove a probe from the registry."""
        if probe_id in self.probes:
            probe = self.probes.pop(probe_id)
            
            # Remove routing aliases
            self.routing_table = {
                k: v for k, v in self.routing_table.items()
                if v != probe_id
            }
            
            logger.info(f"Unregistered probe: {probe_id}")
    
    def get_probe(self, target: str) -> ProbeInfo | None:
        """
        Get probe by ID or alias.
        
        Args:
            target: Probe ID, hostname, or alias
            
        Returns:
            ProbeInfo if found, None otherwise
        """
        # Direct probe ID match
        if target in self.probes:
            return self.probes[target]
        
        # Routing table alias
        if target in self.routing_table:
            probe_id = self.routing_table[target]
            return self.probes.get(probe_id)
        
        return None
    
    def list_probes(
        self,
        probe_type: ProbeType | None = None,
        healthy_only: bool = False
    ) -> list[ProbeInfo]:
        """List registered probes with optional filtering."""
        probes = list(self.probes.values())
        
        if probe_type:
            probes = [p for p in probes if p.probe_type == probe_type]
        
        if healthy_only:
            probes = [p for p in probes if p.healthy and not p.is_stale()]
        
        return probes
    
    def update_health(self, probe_id: str, healthy: bool):
        """Update probe health status."""
        if probe_id in self.probes:
            self.probes[probe_id].healthy = healthy
            self.probes[probe_id].last_heartbeat = datetime.now()
    
    async def call_tool(
        self,
        target: str,
        tool_name: str,
        params: dict[str, Any]
    ) -> MCPCallResult:
        """
        Route and execute an MCP tool call.
        
        Args:
            target: Probe ID, hostname, or alias
            tool_name: Name of the MCP tool to call
            params: Tool parameters
            
        Returns:
            MCPCallResult with success/failure and data
        """
        probe = self.get_probe(target)
        if not probe:
            return MCPCallResult(
                success=False,
                probe_id=target,
                tool_name=tool_name,
                error=f"No probe found for target: {target}"
            )
        
        if not probe.healthy:
            return MCPCallResult(
                success=False,
                probe_id=probe.probe_id,
                tool_name=tool_name,
                error=f"Probe {probe.probe_id} is unhealthy"
            )
        
        # Execute with retry
        import time
        start = time.time()
        
        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()
                
                # MCP tool call format
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"{tool_name}-{time.time()}",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": params
                    }
                }
                
                response = await client.post(
                    probe.endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                duration_ms = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check for MCP error
                    if "error" in data:
                        return MCPCallResult(
                            success=False,
                            probe_id=probe.probe_id,
                            tool_name=tool_name,
                            error=data["error"].get("message", str(data["error"])),
                            duration_ms=duration_ms
                        )
                    
                    # Extract result
                    result = data.get("result", data)
                    
                    self.update_health(probe.probe_id, True)
                    
                    return MCPCallResult(
                        success=True,
                        probe_id=probe.probe_id,
                        tool_name=tool_name,
                        result=result,
                        duration_ms=duration_ms
                    )
                else:
                    logger.warning(
                        f"Probe {probe.probe_id} returned {response.status_code}"
                    )
                    
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1} failed for {probe.probe_id}: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        
        # All retries failed
        self.update_health(probe.probe_id, False)
        duration_ms = (time.time() - start) * 1000
        
        return MCPCallResult(
            success=False,
            probe_id=probe.probe_id,
            tool_name=tool_name,
            error=f"All {self.max_retries} attempts failed",
            duration_ms=duration_ms
        )
    
    async def broadcast(
        self,
        tool_name: str,
        params: dict[str, Any],
        probe_type: ProbeType | None = None,
        parallel: bool = True
    ) -> list[MCPCallResult]:
        """
        Broadcast a tool call to multiple probes.
        
        Args:
            tool_name: MCP tool name
            params: Tool parameters
            probe_type: Filter by probe type (optional)
            parallel: Execute in parallel (default True)
            
        Returns:
            List of results from all targeted probes
        """
        probes = self.list_probes(probe_type=probe_type, healthy_only=True)
        
        if parallel:
            tasks = [
                self.call_tool(p.probe_id, tool_name, params)
                for p in probes
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for probe in probes:
                result = await self.call_tool(probe.probe_id, tool_name, params)
                results.append(result)
            return results


# =============================================================================
# Configuration Loading
# =============================================================================

def load_probe_config(config_path: Path) -> list[dict]:
    """Load probe configuration from YAML/JSON file."""
    import json
    
    if not config_path.exists():
        logger.warning(f"Probe config not found: {config_path}")
        return []
    
    with open(config_path) as f:
        if config_path.suffix == ".json":
            data = json.load(f)
        else:
            import yaml
            data = yaml.safe_load(f)
    
    return data.get("probes", [])


async def create_router_from_config(config_path: Path) -> ProbeRouter:
    """Create a ProbeRouter from configuration file."""
    router = ProbeRouter()
    
    probes = load_probe_config(config_path)
    
    for probe_config in probes:
        router.register_probe(
            probe_id=probe_config["id"],
            probe_type=ProbeType(probe_config["type"]),
            endpoint=probe_config["endpoint"],
            hostname=probe_config["hostname"],
            metadata=probe_config.get("metadata", {})
        )
    
    return router
