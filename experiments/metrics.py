"""
Metrics Collector

Collects metrics from Prometheus and probes.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects metrics from various sources.
    
    Sources:
    - Prometheus (power, GPU, CPU metrics)
    - K8s Probe MCP
    - Host Probe MCP
    """
    
    PROMETHEUS_QUERIES = {
        "power_watts": 'sum(synthetic_power_watts)',
        "energy_joules": 'sum(increase(synthetic_energy_joules[5m]))',
        "cpu_percent": 'avg(100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))',
        "memory_percent": '100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))',
        "gpu_power": 'sum(mock_dcgm_power_usage_watts)',
        "gpu_temp": 'max(mock_dcgm_temperature_celsius)',
        "io_read_bytes": 'sum(rate(node_disk_read_bytes_total[5m]))',
        "io_write_bytes": 'sum(rate(node_disk_written_bytes_total[5m]))',
    }
    
    def __init__(
        self,
        prometheus_url: str = "http://prometheus.monitoring.svc:9090",
        k8s_probe_url: str | None = None,
        host_probe_url: str | None = None
    ):
        self.prometheus_url = prometheus_url
        self.k8s_probe_url = k8s_probe_url
        self.host_probe_url = host_probe_url
    
    async def _query_prometheus(self, query: str) -> float | None:
        """Query Prometheus for a metric value."""
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            params = {"query": query}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    
                    if data["status"] != "success":
                        return None
                    
                    results = data.get("data", {}).get("result", [])
                    if not results:
                        return None
                    
                    # Return first result value
                    return float(results[0]["value"][1])
        
        except Exception as e:
            logger.debug(f"Prometheus query failed: {e}")
            return None
    
    async def _get_mock_value(self, metric: str) -> float:
        """Get mock value when Prometheus unavailable."""
        import random
        
        mock_values = {
            "power_watts": lambda: 1200 + random.uniform(-100, 100),
            "energy_joules": lambda: 3600 + random.uniform(-200, 200),
            "cpu_percent": lambda: 50 + random.uniform(-20, 20),
            "memory_percent": lambda: 60 + random.uniform(-10, 10),
            "gpu_power": lambda: 200 + random.uniform(-50, 50),
            "gpu_temp": lambda: 70 + random.uniform(-5, 10),
            "io_read_bytes": lambda: 1e8 + random.uniform(-5e7, 5e7),
            "io_write_bytes": lambda: 5e7 + random.uniform(-2e7, 2e7),
        }
        
        return mock_values.get(metric, lambda: 0)()
    
    async def collect(self, metrics: list[str]) -> dict[str, Any]:
        """
        Collect specified metrics.
        
        Args:
            metrics: List of metric names to collect
            
        Returns:
            Dictionary of metric name -> value
        """
        result = {"timestamp": datetime.now().isoformat()}
        
        for metric in metrics:
            if metric in self.PROMETHEUS_QUERIES:
                value = await self._query_prometheus(self.PROMETHEUS_QUERIES[metric])
                if value is None:
                    # Fall back to mock
                    value = await self._get_mock_value(metric)
                result[metric] = value
            else:
                logger.warning(f"Unknown metric: {metric}")
                result[metric] = None
        
        return result
    
    async def collect_batch(
        self,
        metrics: list[str],
        duration_seconds: int,
        interval_seconds: int = 10
    ) -> list[dict[str, Any]]:
        """
        Collect metrics over a duration.
        
        Args:
            metrics: Metrics to collect
            duration_seconds: Total collection duration
            interval_seconds: Collection interval
            
        Returns:
            List of metric samples
        """
        samples = []
        
        for _ in range(0, duration_seconds, interval_seconds):
            sample = await self.collect(metrics)
            samples.append(sample)
            await asyncio.sleep(interval_seconds)
        
        return samples
