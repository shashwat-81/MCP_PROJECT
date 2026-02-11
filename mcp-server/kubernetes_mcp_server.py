#!/usr/bin/env python3
"""
Kubernetes MCP Server - A proper Model Context Protocol implementation
Provides Kubernetes cluster management tools via MCP protocol
"""

import asyncio
import subprocess
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from typing import Any

# Initialize MCP server
app = Server("kubernetes-mcp")


def run_kubectl_command(args: list[str]) -> dict[str, Any]:
    """Execute kubectl command and return result"""
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout
            }
        
        return {
            "success": True,
            "output": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timeout after 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Kubernetes management tools"""
    return [
        Tool(
            name="get_pods",
            description="Get list of pods in a namespace or all namespaces. Returns detailed pod information including status, restarts, and resource usage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: all namespaces if not specified)"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "yaml", "wide"],
                        "description": "Output format (default: json)",
                        "default": "json"
                    }
                }
            }
        ),
        Tool(
            name="get_pod_logs",
            description="Get logs from a specific pod. Supports retrieving logs from specific containers and tailing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: default)",
                        "default": "default"
                    },
                    "container": {
                        "type": "string",
                        "description": "Container name (optional, for multi-container pods)"
                    },
                    "tail_lines": {
                        "type": "integer",
                        "description": "Number of recent log lines to retrieve (default: 100)",
                        "default": 100
                    },
                    "previous": {
                        "type": "boolean",
                        "description": "Get logs from previous instance (useful for crashed pods)",
                        "default": False
                    }
                },
                "required": ["pod_name"]
            }
        ),
        Tool(
            name="describe_pod",
            description="Get detailed information about a pod including events, conditions, and resource usage. Essential for troubleshooting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: default)",
                        "default": "default"
                    }
                },
                "required": ["pod_name"]
            }
        ),
        Tool(
            name="get_pod_metrics",
            description="Get resource metrics (CPU, memory) for pods. Requires metrics-server to be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: all namespaces if not specified)"
                    }
                }
            }
        ),
        Tool(
            name="delete_pod",
            description="Delete a pod. The pod will be recreated if managed by a deployment/replicaset. Use for restarting problematic pods.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to delete"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: default)",
                        "default": "default"
                    },
                    "grace_period": {
                        "type": "integer",
                        "description": "Grace period in seconds (default: 30)",
                        "default": 30
                    }
                },
                "required": ["pod_name"]
            }
        ),
        Tool(
            name="get_events",
            description="Get cluster events for troubleshooting. Can be filtered by namespace and shows recent cluster activities.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace (default: all namespaces if not specified)"
                    },
                    "field_selector": {
                        "type": "string",
                        "description": "Filter events (e.g., 'involvedObject.name=pod-name')"
                    }
                }
            }
        ),
        Tool(
            name="get_nodes",
            description="Get information about cluster nodes including capacity, allocatable resources, and conditions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "yaml", "wide"],
                        "description": "Output format (default: json)",
                        "default": "json"
                    }
                }
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Execute Kubernetes tools via MCP protocol"""
    
    if name == "get_pods":
        namespace = arguments.get("namespace", "")
        output_format = arguments.get("output_format", "json")
        
        cmd = ["get", "pods", "-o", output_format]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            if output_format == "json":
                return [TextContent(type="text", text=result["output"])]
            else:
                return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
    
    elif name == "get_pod_logs":
        pod_name = arguments["pod_name"]
        namespace = arguments.get("namespace", "default")
        container = arguments.get("container")
        tail_lines = arguments.get("tail_lines", 100)
        previous = arguments.get("previous", False)
        
        cmd = ["logs", pod_name, "-n", namespace, f"--tail={tail_lines}"]
        if container:
            cmd.extend(["-c", container])
        if previous:
            cmd.append("--previous")
        
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}\nStdout: {result.get('stdout', '')}")]
    
    elif name == "describe_pod":
        pod_name = arguments["pod_name"]
        namespace = arguments.get("namespace", "default")
        
        cmd = ["describe", "pod", pod_name, "-n", namespace]
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
    
    elif name == "get_pod_metrics":
        namespace = arguments.get("namespace", "")
        
        cmd = ["top", "pods"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}\nNote: Requires metrics-server")]
    
    elif name == "delete_pod":
        pod_name = arguments["pod_name"]
        namespace = arguments.get("namespace", "default")
        grace_period = arguments.get("grace_period", 30)
        
        cmd = ["delete", "pod", pod_name, "-n", namespace, f"--grace-period={grace_period}"]
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=f"Successfully deleted pod {pod_name} in namespace {namespace}\n{result['output']}")]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
    
    elif name == "get_events":
        namespace = arguments.get("namespace", "")
        field_selector = arguments.get("field_selector")
        
        cmd = ["get", "events"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        
        if field_selector:
            cmd.extend(["--field-selector", field_selector])
        
        cmd.extend(["--sort-by", ".lastTimestamp"])
        
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
    
    elif name == "get_nodes":
        output_format = arguments.get("output_format", "json")
        
        cmd = ["get", "nodes", "-o", output_format]
        result = run_kubectl_command(cmd)
        
        if result["success"]:
            return [TextContent(type="text", text=result["output"])]
        else:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the Kubernetes MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
