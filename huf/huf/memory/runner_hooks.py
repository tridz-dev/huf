"""Agent Runner Memory Integration Hooks

This module provides the integration points between the HUF Memory System
and the Agent Runner (huf/ai/agent_integration.py).

Usage:
    In agent_integration.py, add the following calls:
    
    1. Before agent execution (around line ~750):
       from huf.memory.runner_hooks import pre_run_hook
       enhanced_prompt = pre_run_hook(agent_doc, enhanced_prompt, conversation)
    
    2. After agent execution (around line ~950):
       from huf.memory.runner_hooks import post_run_hook
       post_run_hook(agent_doc, run_doc, conversation, final_output, history)
"""

import json
from typing import Dict, Any, Optional, List

import frappe


def pre_run_hook(
    agent_doc,
    prompt: str,
    conversation,
    user_id: Optional[str] = None
) -> str:
    """Hook called before agent execution to inject memory context.
    
    This should be called in run_agent_sync after building the enhanced_prompt
    but before calling RunProvider.run().
    
    Integration Point:
        In agent_integration.py, after knowledge context injection (around line 750),
        add:
        
            # Inject memory context
            from huf.memory.runner_hooks import pre_run_hook
            enhanced_prompt = pre_run_hook(agent_doc, enhanced_prompt, conversation)
    
    Args:
        agent_doc: Agent document
        prompt: Current enhanced prompt
        conversation: Conversation document
        user_id: Optional user ID
        
    Returns:
        Enhanced prompt with memory context injected
    """
    try:
        from huf.memory.integration import inject_memory_for_agent
        
        agent_name = agent_doc.name if hasattr(agent_doc, 'name') else str(agent_doc)
        conversation_id = conversation.name if hasattr(conversation, 'name') else str(conversation)
        user_id = user_id or frappe.session.user
        
        return inject_memory_for_agent(
            agent_name=agent_name,
            prompt=prompt,
            conversation_id=conversation_id,
            user_id=user_id
        )
    except Exception as e:
        frappe.log_error(
            f"Memory pre-run hook failed: {str(e)}",
            "Memory Runner Hook"
        )
        return prompt


def post_run_hook(
    agent_doc,
    run_doc,
    conversation,
    agent_response: str,
    conversation_history: Optional[List[Dict]] = None,
    tool_outputs: Optional[List[Dict]] = None
):
    """Hook called after agent execution to capture memories.
    
    This should be called in run_agent_sync after the agent run completes
    but before returning the result.
    
    Integration Point:
        In agent_integration.py, after setting run status to Success (around line 950),
        add:
        
            # Capture memories from this run
            from huf.memory.runner_hooks import post_run_hook
            post_run_hook(agent_doc, run_doc, conversation, final_output, history)
    
    Args:
        agent_doc: Agent document
        run_doc: Agent Run document
        conversation: Conversation document
        agent_response: Agent's final response
        conversation_history: Full conversation history
        tool_outputs: Tool execution results
        
    Returns:
        Capture result dict (or None if skipped)
    """
    try:
        from huf.memory.integration import capture_memory_after_run
        
        agent_name = agent_doc.name if hasattr(agent_doc, 'name') else str(agent_doc)
        run_id = run_doc.name if hasattr(run_doc, 'name') else str(run_doc)
        conversation_id = conversation.name if hasattr(conversation, 'name') else str(conversation)
        
        turn_count = len(conversation_history) if conversation_history else 0
        
        return capture_memory_after_run(
            agent_name=agent_name,
            run_id=run_id,
            conversation_id=conversation_id,
            agent_response=agent_response,
            conversation_history=conversation_history,
            tool_outputs=tool_outputs,
            turn_count=turn_count
        )
    except Exception as e:
        frappe.log_error(
            f"Memory post-run hook failed: {str(e)}",
            "Memory Runner Hook"
        )
        return None


def inject_memory_context_before_run(
    prompt: str,
    agent_doc,
    conversation,
    context: Dict[str, Any]
) -> str:
    """Comprehensive memory injection with full context.
    
    This is an alternative to pre_run_hook that uses the full context dict
    available in agent_integration.py.
    
    Args:
        prompt: Original prompt
        agent_doc: Agent document
        conversation: Conversation document  
        context: Context dict from agent_integration.py
        
    Returns:
        Enhanced prompt with memory injected
    """
    try:
        from huf.memory.integration import MemoryAgentIntegration
        
        agent_name = agent_doc.name if hasattr(agent_doc, 'name') else str(agent_doc)
        conversation_id = conversation.name if hasattr(conversation, 'name') else str(conversation)
        user_id = context.get('user_id') or frappe.session.user
        query = context.get('last_user_message', '')
        
        integration = MemoryAgentIntegration(agent_name)
        
        return integration.inject_memory_context(
            prompt=prompt,
            conversation_id=conversation_id,
            user_id=user_id,
            query=query
        )
        
    except Exception as e:
        frappe.log_error(
            f"Memory context injection failed: {str(e)}",
            "Memory Runner Hook"
        )
        return prompt


def capture_conversation_as_memory(
    agent_doc,
    run_doc,
    conversation,
    messages: List[Dict[str, Any]],
    final_response: str
) -> Dict[str, Any]:
    """Capture conversation as memories.
    
    Utility function for capturing the full conversation context.
    
    Args:
        agent_doc: Agent document
        run_doc: Agent Run document
        conversation: Conversation document
        messages: Full message history
        final_response: Agent's final response
        
    Returns:
        Capture result dict
    """
    try:
        from huf.memory.capture.capture_service import CaptureService
        
        agent_name = agent_doc.name if hasattr(agent_doc, 'name') else str(agent_doc)
        
        service = CaptureService(agent_id=agent_name)
        
        context = {
            "agent_id": agent_name,
            "conversation_id": conversation.name if hasattr(conversation, 'name') else str(conversation),
            "run_id": run_doc.name if hasattr(run_doc, 'name') else str(run_doc),
            "agent_response": final_response,
            "conversation": {
                "messages": messages
            },
            "turn_count": len(messages),
        }
        
        return service.capture(context)
        
    except Exception as e:
        frappe.log_error(
            f"Conversation memory capture failed: {str(e)}",
            "Memory Runner Hook"
        )
        return {
            "capture_triggered": False,
            "error": str(e),
            "records_created": 0
        }


# Helper functions for specific integration scenarios

def should_enable_memory(agent_doc) -> bool:
    """Check if memory should be enabled for this agent run.
    
    Args:
        agent_doc: Agent document
        
    Returns:
        True if memory features should be enabled
    """
    if not agent_doc:
        return False
    
    # Check explicit enable flag
    if getattr(agent_doc, 'enable_memory', False):
        return True
    
    # Check memory policy
    if getattr(agent_doc, 'memory_policy', None):
        return True
    
    return False


def get_memory_config(agent_doc) -> Optional[Dict[str, Any]]:
    """Get memory configuration for an agent.
    
    Args:
        agent_doc: Agent document
        
    Returns:
        Memory config dict or None if not configured
    """
    if not should_enable_memory(agent_doc):
        return None
    
    config = {
        "enabled": True,
        "retrieval_mode": "hybrid",
        "capture_mode": "post_async",
        "inject_max_items": 5,
        "inject_max_tokens": 2000,
    }
    
    # Load from memory policy if available
    policy_name = getattr(agent_doc, 'memory_policy', None)
    if policy_name:
        try:
            policy = frappe.get_doc("Memory Policy", policy_name)
            config.update({
                "retrieval_mode": getattr(policy, 'retrieval_mode', 'hybrid'),
                "capture_mode": getattr(policy, 'capture_mode', 'post_async'),
                "inject_max_items": getattr(policy, 'inject_max_items', 5),
                "inject_max_tokens": getattr(policy, 'inject_max_tokens', 2000),
            })
        except Exception:
            pass
    
    # Override with agent-level settings
    if hasattr(agent_doc, 'memory_max_items'):
        config['inject_max_items'] = agent_doc.memory_max_items
    
    if hasattr(agent_doc, 'memory_in_prompt_budget'):
        config['inject_max_tokens'] = agent_doc.memory_in_prompt_budget
    
    return config
