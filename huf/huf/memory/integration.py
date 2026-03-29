"""Memory System Integration with Agent Runner

This module provides the integration layer between the HUF Memory System
and the Agent Runner. It handles:
1. Memory retrieval and injection before agent execution
2. Memory capture after agent execution
3. Observability and error handling

Usage:
    from huf.memory.integration import integrate_memory_with_agent
    
    # Before running agent
    enhanced_prompt = integrate_memory_with_agent(agent_name, prompt, conversation_id)
    
    # After agent completes
    capture_memory_after_run(run_doc, conversation, agent_response)
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime

import frappe
from frappe import _

from .capture.capture_service import CaptureService, get_capture_service
from .injection import inject_memory_into_prompt, build_memory_context_for_agent
from .retrieval.retrieval_service import MemoryRetrievalService, RetrievalContext
from .retrieval import RetrievalMode


class MemoryAgentIntegration:
    """Integration layer between Memory System and Agent Runner.
    
    This class provides a unified interface for:
    - Pre-execution memory retrieval and injection
    - Post-execution memory capture
    - Agent run observability
    """
    
    def __init__(self, agent_id: str):
        """Initialize integration for an agent.
        
        Args:
            agent_id: Name/ID of the agent
        """
        self.agent_id = agent_id
        self._agent_doc = None
        self._memory_enabled = None
        self._retrieval_service = None
        self._capture_service = None
    
    @property
    def agent_doc(self):
        """Lazy load agent document."""
        if self._agent_doc is None:
            try:
                self._agent_doc = frappe.get_doc("Agent", self.agent_id)
            except frappe.DoesNotExistError:
                return None
        return self._agent_doc
    
    @property
    def memory_enabled(self) -> bool:
        """Check if memory is enabled for this agent."""
        if self._memory_enabled is None:
            if not self.agent_doc:
                self._memory_enabled = False
            else:
                # Check agent's memory_policy field or enable_memory flag
                self._memory_enabled = bool(
                    self.agent_doc.get("memory_policy") or 
                    self.agent_doc.get("enable_memory", False)
                )
        return self._memory_enabled
    
    @property
    def retrieval_service(self) -> MemoryRetrievalService:
        """Get or create retrieval service."""
        if self._retrieval_service is None:
            self._retrieval_service = MemoryRetrievalService()
        return self._retrieval_service
    
    @property
    def capture_service(self) -> CaptureService:
        """Get or create capture service."""
        if self._capture_service is None:
            self._capture_service = get_capture_service(agent_id=self.agent_id)
        return self._capture_service
    
    def get_memory_policy_config(self) -> Optional[Dict[str, Any]]:
        """Get memory policy configuration for the agent.
        
        Returns:
            Dict with policy configuration or None if no policy
        """
        if not self.memory_enabled or not self.agent_doc:
            return None
        
        policy_name = self.agent_doc.get("memory_policy")
        if not policy_name:
            # Return default config
            return {
                "retrieval_mode": "hybrid",
                "capture_mode": "post_async",
                "inject_max_items": 5,
                "inject_max_tokens": 2000,
            }
        
        try:
            policy = frappe.get_doc("Memory Policy", policy_name)
            return {
                "retrieval_mode": policy.get("retrieval_mode", "hybrid"),
                "capture_mode": policy.get("capture_mode", "post_async"),
                "inject_max_items": policy.get("inject_max_items", 5),
                "inject_max_tokens": policy.get("inject_max_tokens", 2000),
                "scope_type": policy.get("scope_type", "conversation"),
            }
        except Exception as e:
            frappe.logger().warning(f"Failed to load memory policy {policy_name}: {e}")
            return None
    
    def inject_memory_context(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        query: Optional[str] = None
    ) -> str:
        """Inject memory context into the agent prompt.
        
        Args:
            prompt: Original agent prompt
            conversation_id: Optional conversation ID
            user_id: Optional user ID
            query: Optional query for relevance ranking
            
        Returns:
            Enhanced prompt with memory context injected
        """
        if not self.memory_enabled:
            return prompt
        
        try:
            config = self.get_memory_policy_config() or {}
            retrieval_mode_str = config.get("retrieval_mode", "hybrid")
            
            # Try to use injection module first
            try:
                return inject_memory_into_prompt(
                    prompt=prompt,
                    agent_name=self.agent_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    query=query
                )
            except Exception as e:
                # Fallback to direct retrieval service
                frappe.logger().debug(f"Injection module failed, using fallback: {e}")
                
                retrieval_mode = RetrievalMode(retrieval_mode_str)
                context = RetrievalContext(
                    agent_name=self.agent_id,
                    conversation_id=conversation_id,
                    user_id=user_id
                )
                
                result = self.retrieval_service.retrieve_by_mode(
                    mode=retrieval_mode,
                    context=context,
                    query=query,
                    inject_max_items=config.get("inject_max_items", 5),
                    inject_max_tokens=config.get("inject_max_tokens", 2000),
                )
                
                if not result.memories:
                    return prompt
                
                # Format memories for injection
                memory_context = self._format_memories_for_prompt(result.memories)
                if memory_context:
                    return f"{memory_context}\n---\n\n{prompt}"
                
                return prompt
                
        except Exception as e:
            frappe.log_error(
                f"Memory injection failed for agent {self.agent_id}: {str(e)}",
                "Memory Integration Error"
            )
            return prompt
    
    def _format_memories_for_prompt(
        self,
        memories: List[Any]
    ) -> str:
        """Format memories as prompt context."""
        if not memories:
            return ""
        
        lines = ["## Relevant Memory\n"]
        
        for memory in memories:
            title = getattr(memory, 'title', 'Untitled')
            memory_type = getattr(memory, 'memory_type', 'memory')
            summary = getattr(memory, 'summary_text', '')
            data = getattr(memory, 'data_json', {})
            
            lines.append(f"### {memory_type.replace('_', ' ').title()}: {title}")
            
            if summary:
                lines.append(summary)
            
            if data and isinstance(data, dict):
                for key, value in data.items():
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def capture_after_run(
        self,
        run_id: str,
        conversation_id: str,
        agent_response: str,
        conversation_history: Optional[List[Dict]] = None,
        tool_outputs: Optional[List[Dict]] = None,
        turn_count: int = 0
    ) -> Dict[str, Any]:
        """Capture memories after agent run completes.
        
        Args:
            run_id: Agent Run document ID
            conversation_id: Conversation document ID
            agent_response: The agent's response text
            conversation_history: Full conversation history
            tool_outputs: Tool execution results
            turn_count: Current turn count
            
        Returns:
            Capture result dict
        """
        if not self.memory_enabled:
            return {
                "capture_triggered": False,
                "reason": "Memory not enabled for agent",
                "records_created": 0
            }
        
        try:
            # Build capture context
            context = {
                "agent_id": self.agent_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "agent_response": agent_response,
                "conversation": {
                    "messages": conversation_history or []
                },
                "tool_outputs": tool_outputs or [],
                "turn_count": turn_count,
                "end_time": datetime.now().isoformat(),
                "source_type": "conversation",
            }
            
            # Execute capture
            result = self.capture_service.capture(context)
            
            # Update run document with capture info
            self._update_run_capture_metrics(run_id, result)
            
            return result
            
        except Exception as e:
            error_msg = f"Memory capture failed: {str(e)}"
            frappe.log_error(error_msg, "Memory Capture Integration")
            
            # Update run with error
            self._update_run_capture_error(run_id, error_msg)
            
            return {
                "capture_triggered": True,
                "error": error_msg,
                "records_created": 0,
                "records_updated": 0
            }
    
    def _update_run_capture_metrics(self, run_id: str, result: Dict[str, Any]):
        """Update Agent Run with capture metrics."""
        if not run_id or not frappe.db.exists("Agent Run", run_id):
            return
        
        try:
            update_data = {
                "memory_capture_triggered": True,
                "memory_capture_mode": result.get("capture_mode", "unknown"),
                "memory_records_created": result.get("records_created", 0),
                "memory_records_updated": result.get("records_updated", 0),
                "memory_records_skipped": 1 if result.get("skipped") else 0,
            }
            
            if result.get("latency_ms"):
                update_data["memory_capture_latency_ms"] = result.get("latency_ms")
            
            frappe.db.set_value("Agent Run", run_id, update_data)
            
        except Exception as e:
            frappe.logger().debug(f"Failed to update run capture metrics: {e}")
    
    def _update_run_capture_error(self, run_id: str, error: str):
        """Update Agent Run with capture error."""
        if not run_id or not frappe.db.exists("Agent Run", run_id):
            return
        
        try:
            frappe.db.set_value("Agent Run", run_id, {
                "memory_capture_triggered": True,
                "memory_error_log": error[:1000]  # Truncate if too long
            })
        except Exception:
            pass


# Convenience functions for direct use

def inject_memory_for_agent(
    agent_name: str,
    prompt: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query: Optional[str] = None
) -> str:
    """Inject memory context into agent prompt.
    
    Main entry point for pre-execution memory injection.
    Called from agent_integration.py before running the agent.
    
    Args:
        agent_name: Name of the agent
        prompt: Original prompt
        conversation_id: Optional conversation ID
        user_id: Optional user ID  
        query: Optional query for relevance
        
    Returns:
        Enhanced prompt with memory context
    """
    integration = MemoryAgentIntegration(agent_name)
    return integration.inject_memory_context(
        prompt=prompt,
        conversation_id=conversation_id,
        user_id=user_id,
        query=query
    )


def capture_memory_after_run(
    agent_name: str,
    run_id: str,
    conversation_id: str,
    agent_response: str,
    conversation_history: Optional[List[Dict]] = None,
    tool_outputs: Optional[List[Dict]] = None,
    turn_count: int = 0
) -> Dict[str, Any]:
    """Capture memories after agent run.
    
    Main entry point for post-execution memory capture.
    Called from agent_integration.py after agent completes.
    
    Args:
        agent_name: Name of the agent
        run_id: Agent Run document ID
        conversation_id: Conversation document ID
        agent_response: The agent's response
        conversation_history: Full conversation history
        tool_outputs: Tool execution results
        turn_count: Current turn count
        
    Returns:
        Capture result dict
    """
    integration = MemoryAgentIntegration(agent_name)
    return integration.capture_after_run(
        run_id=run_id,
        conversation_id=conversation_id,
        agent_response=agent_response,
        conversation_history=conversation_history,
        tool_outputs=tool_outputs,
        turn_count=turn_count
    )


def get_memory_context_for_agent(
    agent_name: str,
    query: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    max_tokens: int = 2000
) -> Dict[str, Any]:
    """Get memory context for an agent without injecting.
    
    Useful for debugging or manual injection scenarios.
    
    Args:
        agent_name: Name of the agent
        query: User query for relevance
        conversation_id: Optional conversation ID
        user_id: Optional user ID
        max_tokens: Max tokens for context
        
    Returns:
        Dict with context_text, memories_used, estimated_tokens
    """
    return build_memory_context_for_agent(
        agent_name=agent_name,
        user_query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        max_tokens=max_tokens
    )


# Hook functions for agent_integration.py

def pre_run_memory_hook(
    agent_doc,
    prompt: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """Hook called before agent execution to inject memory.
    
    Args:
        agent_doc: Agent document
        prompt: Original prompt
        conversation_id: Conversation ID
        user_id: User ID
        
    Returns:
        Enhanced prompt with memory context
    """
    agent_name = agent_doc.name if hasattr(agent_doc, 'name') else agent_doc
    
    # Check if memory is enabled for this agent
    memory_policy = getattr(agent_doc, 'memory_policy', None)
    enable_memory = getattr(agent_doc, 'enable_memory', False)
    
    if not memory_policy and not enable_memory:
        return prompt
    
    return inject_memory_for_agent(
        agent_name=agent_name,
        prompt=prompt,
        conversation_id=conversation_id,
        user_id=user_id
    )


def post_run_memory_hook(
    agent_doc,
    run_doc,
    conversation,
    agent_response: str,
    conversation_history: Optional[List[Dict]] = None,
    tool_outputs: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """Hook called after agent execution to capture memory.
    
    Args:
        agent_doc: Agent document
        run_doc: Agent Run document
        conversation: Conversation document
        agent_response: Agent's response
        conversation_history: Full conversation history
        tool_outputs: Tool execution results
        
    Returns:
        Capture result dict
    """
    agent_name = agent_doc.name if hasattr(agent_doc, 'name') else agent_doc
    
    # Check if memory is enabled for this agent
    memory_policy = getattr(agent_doc, 'memory_policy', None)
    enable_memory = getattr(agent_doc, 'enable_memory', False)
    
    if not memory_policy and not enable_memory:
        return {
            "capture_triggered": False,
            "reason": "Memory not enabled for agent",
            "records_created": 0
        }
    
    # Calculate turn count from history
    turn_count = len(conversation_history) if conversation_history else 0
    
    return capture_memory_after_run(
        agent_name=agent_name,
        run_id=run_doc.name if hasattr(run_doc, 'name') else run_doc,
        conversation_id=conversation.name if hasattr(conversation, 'name') else conversation,
        agent_response=agent_response,
        conversation_history=conversation_history,
        tool_outputs=tool_outputs,
        turn_count=turn_count
    )
