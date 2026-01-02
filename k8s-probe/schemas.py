"""
K8s Probe MCP - Tool Schemas

Defines the MCP tool schemas for the K8s Probe server.
These schemas follow the MCP protocol specification.
"""

from typing import Any

# =============================================================================
# Tool Schemas (MCP Protocol Format)
# =============================================================================

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_cluster_metrics",
        "description": "Get overall cluster resource utilization and node status",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_node_power_state",
        "description": "Get the power/scheduling state of a specific node",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "Name of the node to query"
                }
            },
            "required": ["node_name"]
        }
    },
    {
        "name": "set_node_schedulable",
        "description": "Cordon or uncordon a node (set schedulable state)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "Name of the node to modify"
                },
                "schedulable": {
                    "type": "boolean",
                    "description": "True to uncordon (allow scheduling), False to cordon (prevent scheduling)"
                }
            },
            "required": ["node_name", "schedulable"]
        }
    },
    {
        "name": "drain_node",
        "description": "Safely evict all pods from a node for maintenance or power-down",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "Name of the node to drain"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout for drain operation (default: 300)",
                    "default": 300
                },
                "force": {
                    "type": "boolean",
                    "description": "Force drain even with local storage (default: false)",
                    "default": False
                },
                "ignore_daemonsets": {
                    "type": "boolean",
                    "description": "Ignore DaemonSet pods (default: true)",
                    "default": True
                },
                "respect_pdb": {
                    "type": "boolean",
                    "description": "Respect PodDisruptionBudgets (default: true)",
                    "default": True
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Only simulate, don't execute (default: false)",
                    "default": False
                }
            },
            "required": ["node_name"]
        }
    },
    {
        "name": "get_workload_distribution",
        "description": "Get the distribution of workloads across all nodes",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "consolidate_workloads",
        "description": "Migrate pods to consolidate workloads onto fewer nodes for power savings",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_node_count": {
                    "type": "integer",
                    "description": "Target number of nodes to keep active"
                },
                "exclude_namespaces": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Namespaces to exclude from consolidation",
                    "default": ["kube-system", "calico-system"]
                },
                "exclude_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Nodes to exclude from consolidation",
                    "default": []
                },
                "respect_pdb": {
                    "type": "boolean",
                    "description": "Respect PodDisruptionBudgets (default: true)",
                    "default": True
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Only simulate, don't execute (default: false)",
                    "default": False
                }
            },
            "required": ["target_node_count"]
        }
    },
    {
        "name": "get_gpu_workloads",
        "description": "Get information about GPU workloads in the cluster",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "set_node_labels",
        "description": "Set or remove labels on a node for optimization purposes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_name": {
                    "type": "string",
                    "description": "Name of the node to label"
                },
                "labels": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Labels to set on the node"
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label keys to remove from the node",
                    "default": []
                }
            },
            "required": ["node_name", "labels"]
        }
    }
]


def get_tool_schema(tool_name: str) -> dict[str, Any] | None:
    """Get the schema for a specific tool by name."""
    for tool in TOOLS:
        if tool["name"] == tool_name:
            return tool
    return None


def list_tools() -> list[dict[str, Any]]:
    """Return all available tool schemas."""
    return TOOLS
