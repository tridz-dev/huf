"""HUF Memory System - Retrieval Package.

This package provides memory retrieval, search, and injection functionality
for the HUF Agent Memory system.

Modules:
    retrieval_service: High-level service for memory retrieval
    prompt_injector: Prompt injection for memory context
    memory_search_tool: Search tool implementation for agents
    memory_write_tool: Write tool implementation for agents

Usage:
    from huf.memory.retrieval import MemoryRetrievalService, MemoryPromptInjector
    from huf.memory.retrieval import memory_search, memory_write
"""

# Retrieval Service
from .retrieval_service import (
    MemoryRetrievalService,
    RetrievalContext,
    RetrievalResult,
    retrieve_memories,
    get_memory_by_id,
)

# Prompt Injector
from .prompt_injector import (
    MemoryPromptInjector,
    InjectionConfig,
    build_memory_context,
    inject_memory_into_prompt,
    get_injection_preview,
)

# Tools
from .memory_search_tool import (
    memory_search,
    memory_get_recent,
    memory_get_by_type,
    memory_get_by_scope,
)

from .memory_write_tool import (
    memory_write,
)

__all__ = [
    # Retrieval Service
    "MemoryRetrievalService",
    "RetrievalContext",
    "RetrievalResult",
    "retrieve_memories",
    "get_memory_by_id",
    # Prompt Injector
    "MemoryPromptInjector",
    "InjectionConfig",
    "build_memory_context",
    "inject_memory_into_prompt",
    "get_injection_preview",
    # Tools
    "memory_search",
    "memory_get_recent",
    "memory_get_by_type",
    "memory_get_by_scope",
    "memory_write",
]
