# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
HUF Memory Capture Module

This module provides capture functionality for the HUF Memory System.
Capture modes define HOW and WHEN memory is extracted from conversations.

Available Capture Modes:
    - InPromptCaptureMode: Zero-latency capture during main agent inference
    - PostRunAsyncCaptureMode: Non-blocking async capture via background workers
    - MemoryAgentCaptureMode: Dedicated memory extraction agent
    - RuleOnlyCaptureMode: Deterministic extraction without LLM

Main Service:
    CaptureService: Central orchestrator for all capture operations

Usage:
    from huf.memory.capture import CaptureService, capture_memory
    
    # Using the service
    service = CaptureService(agent_id="my_agent")
    result = service.capture(context={...})
    
    # Direct function
    result = capture_memory(context={...}, agent_id="my_agent")
"""

# Import capture modes
from huf.memory.capture.in_prompt_capture import (
    InPromptCaptureMode,
    InPromptCaptureResponseBuilder,
    create_in_prompt_capture
)

from huf.memory.capture.post_run_capture import (
    PostRunAsyncCaptureMode,
    process_async_capture_job,
    create_post_run_async_capture
)

from huf.memory.capture.memory_agent_capture import (
    MemoryAgentCaptureMode,
    process_memory_agent_job,
    create_memory_agent_capture
)

from huf.memory.capture.rule_capture import (
    RuleOnlyCaptureMode,
    create_rule_only_capture,
    EXAMPLE_RULES
)

from huf.memory.capture.capture_service import (
    CaptureService,
    capture_memory,
    get_capture_service
)

__version__ = "1.0.0"

__all__ = [
    # Capture Modes
    "InPromptCaptureMode",
    "PostRunAsyncCaptureMode",
    "MemoryAgentCaptureMode",
    "RuleOnlyCaptureMode",
    
    # Response Builders
    "InPromptCaptureResponseBuilder",
    
    # Service
    "CaptureService",
    
    # Factory Functions
    "create_in_prompt_capture",
    "create_post_run_async_capture",
    "create_memory_agent_capture",
    "create_rule_only_capture",
    
    # Convenience Functions
    "capture_memory",
    "get_capture_service",
    
    # Background Job Handlers
    "process_async_capture_job",
    "process_memory_agent_job",
    
    # Utilities
    "EXAMPLE_RULES"
]


def get_available_capture_modes() -> list[dict]:
    """
    Get a list of all available capture modes with their descriptions.
    
    Returns:
        List of mode information dictionaries
    """
    return [
        {
            "id": "in_prompt",
            "name": "In-Prompt Capture",
            "description": "Memory extracted during main agent inference with zero additional latency",
            "latency_impact": "zero",
            "producer": "main_agent",
            "use_case": "Real-time capture where agent can self-reflect"
        },
        {
            "id": "post_async",
            "name": "Post-Run Async",
            "description": "Non-blocking async capture via background workers with eventual consistency",
            "latency_impact": "zero",
            "producer": "post_run_processor",
            "use_case": "High-traffic agents where latency matters"
        },
        {
            "id": "specialized_agent",
            "name": "Specialized Memory Agent",
            "description": "Dedicated agent for memory extraction, can use cheaper/faster models",
            "latency_impact": "variable",
            "producer": "memory_agent",
            "use_case": "High-quality extraction with configurable resources"
        },
        {
            "id": "rule_only",
            "name": "Rule-Only Capture",
            "description": "Deterministic extraction using rules without LLM inference",
            "latency_impact": "minimal",
            "producer": "rule_engine",
            "use_case": "Structured data extraction with predictable patterns"
        }
    ]


def create_capture_mode(mode_id: str, config: dict):
    """
    Factory function to create a capture mode instance by ID.
    
    Args:
        mode_id: Capture mode identifier (in_prompt, post_async, etc.)
        config: Configuration dictionary for the mode
        
    Returns:
        Capture mode instance
        
    Raises:
        ValueError: If mode_id is not recognized
        
    Example:
        mode = create_capture_mode("rule_only", {"rules": [...]})
        result = mode.execute(context)
    """
    mode_map = {
        "in_prompt": InPromptCaptureMode,
        "post_async": PostRunAsyncCaptureMode,
        "post_sync": PostRunAsyncCaptureMode,
        "specialized_agent": MemoryAgentCaptureMode,
        "rule_only": RuleOnlyCaptureMode
    }
    
    mode_class = mode_map.get(mode_id)
    if not mode_class:
        raise ValueError(
            f"Unknown capture mode: {mode_id}. "
            f"Available modes: {list(mode_map.keys())}"
        )
    
    return mode_class(config)
