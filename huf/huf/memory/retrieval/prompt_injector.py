"""Prompt Injector - Memory context injection for agent prompts.

This module provides prompt injection functionality that automatically
includes relevant memories in agent prompts based on retrieval mode.

Based on:
    - PRD Section 15: Retrieval Model (Inject Mode)
    - CAPTURE_RETRIEVAL.md Section 3.2

Dependencies:
    - E1: Memory Retrieval Service (COMPLETE)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
import frappe
from frappe import _

from .retrieval_service import MemoryRetrievalService, RetrievalContext, RetrievalMode


@dataclass
class InjectionConfig:
    """Configuration for memory prompt injection.
    
    Controls how memories are formatted and injected into prompts.
    """
    # Token budget
    max_tokens: int = 2000
    max_items: int = 5
    
    # Formatting options
    format_style: str = "markdown"  # markdown, json, xml
    include_metadata: bool = False
    include_timestamps: bool = False
    
    # Section headers
    section_header: str = "## Relevant Memory"
    empty_message: str = ""
    
    # Memory type grouping
    group_by_type: bool = True
    sort_by: str = "importance"  # importance, recency, relevance


class MemoryPromptInjector:
    """Injects memory context into agent prompts.
    
    Provides methods to retrieve and format memories for prompt injection,
    supporting multiple output formats and configuration options.
    
    Usage:
        injector = MemoryPromptInjector()
        context_block = injector.build_memory_context(
            agent_name="MyAgent",
            conversation_id="CONV-001",
        )
        full_prompt = injector.inject_into_prompt(system_prompt, context_block)
    """
    
    # Format templates for different styles
    TEMPLATES = {
        "markdown": {
            "section_header": "## {header}",
            "memory_header": "### {memory_type}: {title}",
            "memory_item": "- {key}: {value}",
            "memory_summary": "{summary}",
            "separator": "\n",
        },
        "json": {
            "section_header": "",
            "memory_wrapper": "\"memories\": {memories}",
            "memory_object": '{{"title": "{title}", "type": "{memory_type}", "data": {data}}}',
        },
        "xml": {
            "section_header": "<memories>",
            "memory_header": "<memory type=\"{memory_type}\" title=\"{title}\">",
            "memory_footer": "</memory>",
            "section_footer": "</memories>",
        },
    }
    
    def __init__(self, config: Optional[InjectionConfig] = None):
        """Initialize the prompt injector.
        
        Args:
            config: Optional injection configuration
        """
        self.config = config or InjectionConfig()
        self.retrieval_service = MemoryRetrievalService()
    
    def build_memory_context(
        self,
        agent_name: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        query: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Build memory context block for prompt injection.
        
        Retrieves relevant memories and formats them according to the
        configured style for inclusion in the system prompt.
        
        Args:
            agent_name: Name of the agent
            conversation_id: Optional conversation context
            user_id: Optional user context
            query: Optional query for relevance ranking
            run_id: Optional run context
        
        Returns:
            Formatted memory context string (empty if no memories)
        """
        # Create retrieval context
        context = RetrievalContext(
            agent_name=agent_name,
            conversation_id=conversation_id,
            user_id=user_id,
            run_id=run_id,
        )
        
        # Retrieve memories for injection
        result = self.retrieval_service.retrieve_for_injection(
            context=context,
            query=query,
            max_items=self.config.max_items,
            max_tokens=self.config.max_tokens,
        )
        
        if not result.memories:
            return self.config.empty_message
        
        # Format based on style
        if self.config.format_style == "markdown":
            return self._format_markdown(result.memories)
        elif self.config.format_style == "json":
            return self._format_json(result.memories)
        elif self.config.format_style == "xml":
            return self._format_xml(result.memories)
        else:
            return self._format_markdown(result.memories)
    
    def inject_into_prompt(
        self,
        system_prompt: str,
        memory_context: str,
        position: str = "after_instructions",
    ) -> str:
        """Inject memory context into a system prompt.
        
        Args:
            system_prompt: Original system prompt
            memory_context: Formatted memory context block
            position: Where to inject - "beginning", "after_instructions", "end"
        
        Returns:
            Combined prompt with memory context injected
        """
        if not memory_context.strip():
            return system_prompt
        
        if position == "beginning":
            return f"{memory_context}\n\n{system_prompt}"
        
        elif position == "end":
            return f"{system_prompt}\n\n{memory_context}"
        
        elif position == "after_instructions":
            # Try to find a good insertion point after core instructions
            # but before specific task instructions
            lines = system_prompt.split("\n")
            
            # Look for common section markers
            insertion_point = len(lines)
            for i, line in enumerate(lines):
                lower = line.lower()
                if any(marker in lower for marker in [
                    "---", "context:", "task:", "instructions:",
                    "you are given", "your task is"
                ]):
                    insertion_point = i
                    break
            
            # Insert memory context
            new_lines = (
                lines[:insertion_point] +
                ["", memory_context, ""] +
                lines[insertion_point:]
            )
            return "\n".join(new_lines)
        
        else:
            # Default: append to beginning
            return f"{memory_context}\n\n{system_prompt}"
    
    def inject_for_agent(
        self,
        agent_name: str,
        system_prompt: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full injection workflow for an agent.
        
        Combines memory retrieval and prompt injection in one call.
        
        Args:
            agent_name: Name of the agent
            system_prompt: Original system prompt
            conversation_id: Optional conversation context
            user_id: Optional user context
            query: Optional query for relevance
        
        Returns:
            Dict with injected_prompt, memories_used, and metadata
        """
        # Build memory context
        memory_context = self.build_memory_context(
            agent_name=agent_name,
            conversation_id=conversation_id,
            user_id=user_id,
            query=query,
        )
        
        # Inject into prompt
        injected_prompt = self.inject_into_prompt(
            system_prompt=system_prompt,
            memory_context=memory_context,
            position="after_instructions",
        )
        
        # Get metadata about injection
        context = RetrievalContext(
            agent_name=agent_name,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        result = self.retrieval_service.retrieve_for_injection(
            context=context,
            query=query,
            max_items=self.config.max_items,
            max_tokens=self.config.max_tokens,
        )
        
        return {
            "injected_prompt": injected_prompt,
            "original_prompt": system_prompt,
            "memory_context": memory_context,
            "memories_used": [
                {
                    "name": m.name,
                    "title": m.title,
                    "memory_type": m.memory_type,
                    "importance": m.importance_score,
                }
                for m in result.memories
            ],
            "metadata": {
                "memory_count": len(result.memories),
                "estimated_tokens": result.estimated_tokens,
                "format_style": self.config.format_style,
            }
        }
    
    def _format_markdown(self, memories: List[Any]) -> str:
        """Format memories in markdown style.
        
        Example output:
            ## Relevant Memory
            
            ### Preference: User Dark Mode
            - Theme: dark
            - Preference Source: explicit
            
            ### Fact: API Endpoint
            - URL: https://api.example.com/v1
        """
        lines = [f"## {self.config.section_header.lstrip('#').strip()}"]
        lines.append("")
        
        # Group by memory type if configured
        if self.config.group_by_type:
            grouped = {}
            for m in memories:
                mtype = m.memory_type.replace("_", " ").title()
                if mtype not in grouped:
                    grouped[mtype] = []
                grouped[mtype].append(m)
            
            for mtype, type_memories in grouped.items():
                for m in type_memories:
                    lines.append(f"### {mtype}: {m.title}")
                    lines.append("")
                    
                    # Add summary if available
                    if m.summary_text:
                        lines.append(m.summary_text)
                        lines.append("")
                    
                    # Add data as key-value pairs
                    if m.data_json:
                        if isinstance(m.data_json, dict):
                            for key, value in m.data_json.items():
                                if isinstance(value, (dict, list)):
                                    value = json.dumps(value)
                                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
                        else:
                            lines.append(f"- Data: {m.data_json}")
                    
                    if self.config.include_metadata:
                        lines.append(f"- Confidence: {m.confidence}")
                        lines.append(f"- Importance: {m.importance_score}")
                    
                    lines.append("")
        else:
            # Simple list format
            for m in memories:
                lines.append(f"### {m.memory_type}: {m.title}")
                lines.append("")
                
                if m.summary_text:
                    lines.append(m.summary_text)
                    lines.append("")
                
                if m.data_json:
                    if isinstance(m.data_json, dict):
                        for key, value in m.data_json.items():
                            lines.append(f"- {key}: {value}")
                    else:
                        lines.append(f"- {m.data_json}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_json(self, memories: List[Any]) -> str:
        """Format memories as JSON."""
        memory_list = []
        for m in memories:
            entry = {
                "title": m.title,
                "memory_type": m.memory_type,
                "data": m.data_json,
            }
            if m.summary_text:
                entry["summary"] = m.summary_text
            if self.config.include_metadata:
                entry["confidence"] = m.confidence
                entry["importance"] = m.importance_score
            memory_list.append(entry)
        
        return json.dumps({"memories": memory_list}, indent=2)
    
    def _format_xml(self, memories: List[Any]) -> str:
        """Format memories as XML."""
        lines = ["<memories>"]
        
        for m in memories:
            lines.append(f'  <memory type="{m.memory_type}" title="{m.title}">')
            
            if m.summary_text:
                lines.append(f"    <summary>{m.summary_text}</summary>")
            
            if m.data_json:
                lines.append(f"    <data>{json.dumps(m.data_json)}</data>")
            
            if self.config.include_metadata:
                lines.append(f'    <confidence>{m.confidence}</confidence>')
                lines.append(f'    <importance>{m.importance_score}</importance>')
            
            lines.append("  </memory>")
        
        lines.append("</memories>")
        return "\n".join(lines)


# Convenience functions for direct use

def build_memory_context(
    agent_name: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query: Optional[str] = None,
    max_tokens: int = 2000,
    max_items: int = 5,
    format_style: str = "markdown",
) -> str:
    """Build memory context block for prompt injection.
    
    Convenience function that creates a MemoryPromptInjector with
    the specified configuration and builds the context.
    
    Args:
        agent_name: Name of the agent
        conversation_id: Optional conversation context
        user_id: Optional user context
        query: Optional query for relevance
        max_tokens: Maximum tokens for memory content
        max_items: Maximum memory items to include
        format_style: Output format (markdown, json, xml)
    
    Returns:
        Formatted memory context string
    """
    config = InjectionConfig(
        max_tokens=max_tokens,
        max_items=max_items,
        format_style=format_style,
    )
    injector = MemoryPromptInjector(config)
    return injector.build_memory_context(
        agent_name=agent_name,
        conversation_id=conversation_id,
        user_id=user_id,
        query=query,
    )


def inject_memory_into_prompt(
    system_prompt: str,
    agent_name: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query: Optional[str] = None,
    max_tokens: int = 2000,
    max_items: int = 5,
    position: str = "after_instructions",
) -> str:
    """Inject memory context into a system prompt.
    
    Convenience function for one-shot memory injection.
    
    Args:
        system_prompt: Original system prompt
        agent_name: Name of the agent
        conversation_id: Optional conversation context
        user_id: Optional user context
        query: Optional query for relevance
        max_tokens: Maximum tokens for memory content
        max_items: Maximum memory items
        position: Injection position (beginning, after_instructions, end)
    
    Returns:
        Prompt with memory context injected
    """
    config = InjectionConfig(
        max_tokens=max_tokens,
        max_items=max_items,
    )
    injector = MemoryPromptInjector(config)
    
    memory_context = injector.build_memory_context(
        agent_name=agent_name,
        conversation_id=conversation_id,
        user_id=user_id,
        query=query,
    )
    
    return injector.inject_into_prompt(
        system_prompt=system_prompt,
        memory_context=memory_context,
        position=position,
    )


@frappe.whitelist()
def get_injection_preview(
    agent_name: str,
    conversation_id: Optional[str] = None,
    query: Optional[str] = None,
    max_items: int = 5,
) -> Dict[str, Any]:
    """API endpoint to preview memory injection for debugging.
    
    Args:
        agent_name: Name of the agent
        conversation_id: Optional conversation context
        query: Optional query for relevance
        max_items: Maximum memories to preview
    
    Returns:
        Dict with memory_context preview and metadata
    """
    try:
        config = InjectionConfig(max_items=max_items)
        injector = MemoryPromptInjector(config)
        
        memory_context = injector.build_memory_context(
            agent_name=agent_name,
            conversation_id=conversation_id,
            query=query,
        )
        
        # Get retrieval metadata
        context = RetrievalContext(
            agent_name=agent_name,
            conversation_id=conversation_id,
        )
        result = injector.retrieval_service.retrieve_for_injection(
            context=context,
            query=query,
            max_items=max_items,
        )
        
        return {
            "success": True,
            "memory_context": memory_context,
            "memories_found": len(result.memories),
            "estimated_tokens": result.estimated_tokens,
            "memories": [
                {
                    "name": m.name,
                    "title": m.title,
                    "memory_type": m.memory_type,
                    "importance": m.importance_score,
                    "confidence": m.confidence,
                }
                for m in result.memories
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
