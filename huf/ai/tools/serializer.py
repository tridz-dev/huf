# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tool serialization utilities for multi-provider AI agents.

This module converts custom FunctionTool objects (created in sdk_tools.py)
into the standard JSON schema format that providers like OpenAI, OpenRouter,
Anthropic, etc. expect for function/tool calling.
"""

from typing import List, Dict, Any


def serialize_tools(tools: list) -> List[Dict[str, Any]]:
    """
    Convert custom FunctionTool objects into provider-agnostic schema.

    Args:
        tools: List of FunctionTool objects created by sdk_tools.create_agent_tools

    Returns:
        List[dict]: Tools serialized into OpenAI/OpenRouter-compatible schema
    """
    serialized = []
    for tool in tools or []:
        serialized.append({
            "type": "function",
            "function": {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", "") or "",
                "parameters": getattr(tool, "params_json_schema", {}) or {}
            }
        })
    return serialized
