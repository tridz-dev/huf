"""HUF Memory System - Retrieval Layer.

This package implements the memory retrieval, search, and injection
functionality for the HUF Agent Memory system.

Modules:
    retrieval: Retrieval modes (inject, tool_only, hybrid)
    search: Memory search with filters and ranking
    injection: Prompt injection for memory context
    integration: Agent runner integration

Based on:
    - PRD Section 15: Retrieval Model
    - CAPTURE_RETRIEVAL.md: Technical Specifications
"""

from .retrieval import (
    RetrievalMode,
    MemoryRetrievalConfig,
    MemoryRetrievalMode,
    InjectRetrievalMode,
    ToolOnlyRetrievalMode,
    HybridRetrievalMode,
    get_retrieval_mode,
    resolve_retrieval_mode_for_agent,
)

from .search import (
    MemorySearchResult,
    MemoryFilterBuilder,
    MemoryRanker,
    MemorySearcher,
    memory_search,
    get_recent_memories,
    get_high_importance_memories,
)

from .injection import (
    MemoryContextBuilder,
    MemoryPromptInjector,
    build_memory_context_for_agent,
    inject_memory_into_prompt,
)

from .integration import (
    MemoryAgentIntegration,
    inject_memory_for_agent,
    capture_memory_after_run,
    get_memory_context_for_agent,
    pre_run_memory_hook,
    post_run_memory_hook,
)

__all__ = [
    # Retrieval
    "RetrievalMode",
    "MemoryRetrievalConfig",
    "MemoryRetrievalMode",
    "InjectRetrievalMode",
    "ToolOnlyRetrievalMode",
    "HybridRetrievalMode",
    "get_retrieval_mode",
    "resolve_retrieval_mode_for_agent",
    # Search
    "MemorySearchResult",
    "MemoryFilterBuilder",
    "MemoryRanker",
    "MemorySearcher",
    "memory_search",
    "get_recent_memories",
    "get_high_importance_memories",
    # Injection
    "MemoryContextBuilder",
    "MemoryPromptInjector",
    "build_memory_context_for_agent",
    "inject_memory_into_prompt",
    # Integration
    "MemoryAgentIntegration",
    "inject_memory_for_agent",
    "capture_memory_after_run",
    "get_memory_context_for_agent",
    "pre_run_memory_hook",
    "post_run_memory_hook",
]
