"""
Workload Generator

Generates K8s resources from workload profiles.
Integrates with Hardware Safety Monitor.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from .profiles import WorkloadProfile, Resources

logger = logging.getLogger(__name__)


class WorkloadGenerator:
    """
    Generates K8s workload resources.
    
    Usage:
        generator = WorkloadGenerator()
        manifest = generator.generate_deployment(profile)
        await generator.apply(manifest)
    """
    
    def __init__(self, kubeconfig: str | None = None):
        self.kubeconfig = kubeconfig
        self._deployed: list[dict] = []
    
    def _base_metadata(self, profile: WorkloadProfile) -> dict:
        """Generate base metadata for resources."""
        return {
            "name": profile.name,
            "namespace": profile.namespace,
            "labels": profile.labels,
            "annotations": {
                "vsf.seerintel.ai/profile": profile.pattern,
                "vsf.seerintel.ai/intensity": str(profile.intensity),
                "vsf.seerintel.ai/created": datetime.now().isoformat()
            }
        }
    
    def _container_spec(self, profile: WorkloadProfile) -> dict:
        """Generate container spec."""
        resources = {
            "requests": {
                "cpu": profile.resources.requests.cpu,
                "memory": profile.resources.requests.memory
            },
            "limits": {
                "cpu": profile.resources.limits.cpu,
                "memory": profile.resources.limits.memory
            }
        }
        
        # Add GPU if specified
        if profile.resources.requests.gpu:
            resources["requests"]["nvidia.com/gpu"] = profile.resources.requests.gpu
            resources["limits"]["nvidia.com/gpu"] = profile.resources.limits.gpu
        
        return {
            "name": "workload",
            "image": profile.image,
            "command": profile.command,
            "resources": resources
        }
    
    def _pod_spec(self, profile: WorkloadProfile) -> dict:
        """Generate pod spec."""
        spec = {
            "containers": [self._container_spec(profile)]
        }
        
        if profile.node_selector:
            spec["nodeSelector"] = profile.node_selector
        
        if profile.tolerations:
            spec["tolerations"] = profile.tolerations
        
        return spec
    
    def generate_deployment(self, profile: WorkloadProfile) -> dict:
        """
        Generate a Deployment manifest.
        
        Args:
            profile: Workload profile
            
        Returns:
            K8s Deployment manifest dict
        """
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": self._base_metadata(profile),
            "spec": {
                "replicas": profile.replicas,
                "selector": {
                    "matchLabels": {"app": profile.name}
                },
                "template": {
                    "metadata": {
                        "labels": {"app": profile.name, **profile.labels}
                    },
                    "spec": self._pod_spec(profile)
                }
            }
        }
    
    def generate_job(self, profile: WorkloadProfile) -> dict:
        """
        Generate a Job manifest.
        
        Args:
            profile: Workload profile
            
        Returns:
            K8s Job manifest dict
        """
        pod_spec = self._pod_spec(profile)
        pod_spec["restartPolicy"] = "Never"
        
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": self._base_metadata(profile),
            "spec": {
                "parallelism": profile.parallelism or 1,
                "completions": profile.completions or 1,
                "backoffLimit": 3,
                "template": {
                    "metadata": {
                        "labels": {"app": profile.name, **profile.labels}
                    },
                    "spec": pod_spec
                }
            }
        }
    
    def generate(self, profile: WorkloadProfile) -> dict:
        """
        Generate manifest based on profile type.
        
        Args:
            profile: Workload profile
            
        Returns:
            K8s manifest dict
        """
        if profile.type == "deployment":
            return self.generate_deployment(profile)
        elif profile.type == "job":
            return self.generate_job(profile)
        else:
            raise ValueError(f"Unsupported workload type: {profile.type}")
    
    async def apply(self, manifest: dict) -> bool:
        """
        Apply manifest to cluster.
        
        Args:
            manifest: K8s manifest dict
            
        Returns:
            True if successful
        """
        manifest_json = json.dumps(manifest)
        
        cmd = ["kubectl", "apply", "-f", "-"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        
        logger.info(f"Applying {manifest['kind']} {manifest['metadata']['name']}")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(manifest_json.encode())
            
            if proc.returncode != 0:
                error = stderr.decode()
                logger.error(f"Failed to apply manifest: {error}")
                
                if "quota" in error.lower():
                    raise ResourceError("ResourceQuota exceeded")
                raise RuntimeError(error)
            
            self._deployed.append(manifest)
            logger.info(f"Successfully applied {manifest['kind']} {manifest['metadata']['name']}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying manifest: {e}")
            raise
    
    async def delete(self, manifest: dict) -> bool:
        """
        Delete resource from cluster.
        
        Args:
            manifest: K8s manifest dict
            
        Returns:
            True if successful
        """
        kind = manifest["kind"].lower()
        name = manifest["metadata"]["name"]
        namespace = manifest["metadata"]["namespace"]
        
        cmd = [
            "kubectl", "delete", kind, name,
            "-n", namespace,
            "--ignore-not-found"
        ]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        
        logger.info(f"Deleting {kind} {name}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        return proc.returncode == 0
    
    async def cleanup(self) -> int:
        """
        Delete all deployed resources.
        
        Returns:
            Number of resources deleted
        """
        count = 0
        for manifest in reversed(self._deployed):
            if await self.delete(manifest):
                count += 1
        
        self._deployed.clear()
        logger.info(f"Cleaned up {count} resources")
        return count


class ResourceError(Exception):
    """Raised when a resource error occurs."""
    pass
