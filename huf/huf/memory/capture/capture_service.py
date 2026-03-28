# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Memory Capture Service - Main Orchestrator

Central service for orchestrating memory capture operations across
different capture modes. Provides a unified interface for:
- Capture mode selection and execution
- Policy-based capture configuration
- Trigger evaluation
- Record persistence
- Error handling and observability

Usage:
    from huf.memory.capture import CaptureService
    
    service = CaptureService(agent_id="my_agent")
    result = service.capture(context={
        "conversation_id": "conv_123",
        "agent_response": "...",
        "conversation": {...}
    })
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime

# Import capture modes
from huf.memory.capture.in_prompt_capture import InPromptCaptureMode, create_in_prompt_capture
from huf.memory.capture.post_run_capture import PostRunAsyncCaptureMode, create_post_run_async_capture
from huf.memory.capture.memory_agent_capture import MemoryAgentCaptureMode, create_memory_agent_capture
from huf.memory.capture.rule_capture import RuleOnlyCaptureMode, create_rule_only_capture


class CaptureService:
    """
    Main orchestrator for memory capture operations.
    
    This service provides a unified interface for all memory capture
    functionality, handling:
    - Policy resolution
    - Capture mode selection
    - Trigger evaluation
    - Record persistence
    - Error handling
    
    Example:
        service = CaptureService(agent_id="my_agent")
        
        # Simple capture
        result = service.capture(context={...})
        
        # Capture with specific mode
        result = service.capture(
            context={...},
            mode="rule_only",
            config={"rules": [...]}
        )
    """
    
    # Map of capture mode IDs to their classes
    CAPTURE_MODES = {
        "in_prompt": InPromptCaptureMode,
        "post_async": PostRunAsyncCaptureMode,
        "post_sync": PostRunAsyncCaptureMode,  # Uses sync execution path
        "specialized_agent": MemoryAgentCaptureMode,
        "rule_only": RuleOnlyCaptureMode
    }
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the capture service.
        
        Args:
            agent_id: Optional agent ID to load policy from
            policy_id: Optional explicit policy ID
            config: Optional explicit configuration
        """
        self.agent_id = agent_id
        self.policy_id = policy_id
        self.config = config or {}
        self._policy = None
        
        # Load policy if agent_id provided
        if agent_id and not config:
            self._load_policy_for_agent(agent_id)
    
    def _load_policy_for_agent(self, agent_id: str):
        """Load memory policy configuration for an agent."""
        try:
            if not frappe.db.exists("Agent", agent_id):
                frappe.logger().warning(f"Agent {agent_id} not found")
                return
            
            agent = frappe.get_doc("Agent", agent_id)
            
            # Get memory policy from agent
            policy_name = agent.get("memory_policy")
            
            if policy_name and frappe.db.exists("Memory Policy", policy_name):
                self.policy_id = policy_name
                policy = frappe.get_doc("Memory Policy", policy_name)
                self._policy = policy
                self.config = self._policy_to_config(policy)
            else:
                # Use default configuration
                self.config = self._default_config()
                
        except Exception as e:
            frappe.logger().error(f"Failed to load policy for agent {agent_id}: {e}")
            self.config = self._default_config()
    
    def _policy_to_config(self, policy) -> Dict[str, Any]:
        """Convert Memory Policy document to configuration dict."""
        return {
            "capture_mode": policy.get("capture_owner", "post_async"),
            "capture": {
                "capture_mode": policy.get("capture_owner", "post_async"),
                "memory_agent": policy.get("memory_agent"),
                "capture_prompt": policy.get("capture_prompt"),
                "schema_json": self._parse_json_field(policy.get("capture_schema_json")),
                "require_json_schema_match": policy.get("require_json_schema_match", False),
                "allow_open_schema": policy.get("allow_open_schema", True)
            },
            "scope_type": policy.get("default_scope_type", "conversation"),
            "visibility": policy.get("visibility_default", "private"),
            "allow_update_existing": policy.get("allow_update_existing", True),
            "allow_merge": policy.get("allow_merge", False),
            "ttl_days": policy.get("ttl_days"),
            "enable_fts_index": policy.get("enable_fts_index", True),
            "enable_vector_index": policy.get("enable_vector_index", False),
            "triggers": self._parse_triggers(policy)
        }
    
    def _parse_json_field(self, value) -> Optional[Dict]:
        """Parse JSON string to dict."""
        if not value:
            return None
        if isinstance(value, dict):
            return value
        try:
            import json
            return json.loads(value)
        except:
            return None
    
    def _parse_triggers(self, policy) -> List[Dict]:
        """Parse trigger configuration from policy."""
        triggers = []
        
        # Add frequency-based trigger
        freq_type = policy.get("capture_frequency_type", "every_run")
        if freq_type:
            trigger = {"trigger_type": freq_type}
            if freq_type in ["every_n_runs", "every_n_turns"]:
                trigger["n"] = policy.get("capture_frequency_value", 1)
            triggers.append(trigger)
        
        return triggers
    
    def _default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "capture_mode": "post_async",
            "scope_type": "conversation",
            "visibility": "private",
            "enable_fts_index": True
        }
    
    def capture(
        self,
        context: Dict[str, Any],
        mode: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Execute memory capture with the configured or specified mode.
        
        Args:
            context: Capture context containing conversation, run, etc.
            mode: Optional override for capture mode
            config: Optional override for capture configuration
            force: Force capture regardless of triggers
            
        Returns:
            Capture result dict with records_created, errors, etc.
        """
        start_time = datetime.now()
        
        # Determine capture mode
        capture_mode = mode or self.config.get("capture_mode", "post_async")
        capture_config = config or self.config.get("capture", self.config)
        
        # Evaluate triggers (unless forced)
        if not force:
            should_capture, trigger_reason = self._should_capture(context)
            if not should_capture:
                return {
                    "capture_triggered": False,
                    "capture_mode": capture_mode,
                    "reason": trigger_reason,
                    "records_created": 0,
                    "records_updated": 0,
                    "latency_ms": self._calculate_latency(start_time)
                }
        
        # Get capture mode instance
        try:
            capture_instance = self._get_capture_mode(capture_mode, capture_config)
        except ValueError as e:
            return {
                "capture_triggered": True,
                "capture_mode": capture_mode,
                "error": str(e),
                "records_created": 0,
                "records_updated": 0,
                "latency_ms": self._calculate_latency(start_time)
            }
        
        # Execute capture
        try:
            if capture_mode == "in_prompt":
                # In-prompt mode expects response_data in context
                result = capture_instance.execute(
                    response_data=context.get("response_data", {}),
                    context=context
                )
            else:
                # Other modes use context directly
                result = capture_instance.execute(context)
            
            # Persist records if not async
            if not result.get("async") and result.get("records_created", 0) > 0:
                record_ids = self._persist_records(
                    result.get("payload", {}).get("records", []),
                    context
                )
                result["record_ids"] = record_ids
            
            result["capture_triggered"] = True
            result["capture_mode"] = capture_mode
            result["latency_ms"] = result.get("latency_ms", self._calculate_latency(start_time))
            
            return result
            
        except Exception as e:
            error_msg = f"Capture execution failed: {str(e)}"
            frappe.log_error(error_msg, "Capture Service")
            
            return {
                "capture_triggered": True,
                "capture_mode": capture_mode,
                "error": error_msg,
                "records_created": 0,
                "records_updated": 0,
                "latency_ms": self._calculate_latency(start_time)
            }
    
    def _should_capture(self, context: Dict[str, Any]) -> tuple[bool, str]:
        """
        Evaluate if capture should run based on triggers.
        
        Args:
            context: Capture context
            
        Returns:
            Tuple of (should_capture, reason)
        """
        triggers = self.config.get("triggers", [])
        
        # Default: always capture if no triggers specified
        if not triggers:
            return True, "No triggers configured - defaulting to capture"
        
        # Evaluate each trigger
        for trigger in triggers:
            trigger_type = trigger.get("trigger_type", "every_run")
            
            if trigger_type == "every_run":
                return True, "every_run trigger matched"
            
            elif trigger_type == "every_n_runs":
                n = trigger.get("n", 1)
                run_count = context.get("run_count", 0)
                if run_count % n == 0:
                    return True, f"every_n_runs trigger matched (run {run_count})"
            
            elif trigger_type == "every_n_turns":
                n = trigger.get("n", 5)
                turn_count = context.get("turn_count", 0)
                if turn_count % n == 0:
                    return True, f"every_n_turns trigger matched (turn {turn_count})"
            
            elif trigger_type == "conversation_end":
                if context.get("is_conversation_end"):
                    return True, "conversation_end trigger matched"
            
            elif trigger_type == "manual":
                if context.get("manual_trigger"):
                    return True, "manual trigger matched"
        
        return False, "No triggers matched"
    
    def _get_capture_mode(
        self,
        mode_id: str,
        config: Dict[str, Any]
    ):
        """
        Get capture mode instance by ID.
        
        Args:
            mode_id: Capture mode identifier
            config: Configuration for the mode
            
        Returns:
            Capture mode instance
            
        Raises:
            ValueError: If mode_id is not recognized
        """
        mode_class = self.CAPTURE_MODES.get(mode_id)
        
        if not mode_class:
            raise ValueError(f"Unknown capture mode: {mode_id}")
        
        return mode_class(config)
    
    def _persist_records(
        self,
        records: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[str]:
        """
        Persist memory records to the database.
        
        Args:
            records: List of memory record dicts
            context: Capture context
            
        Returns:
            List of created record IDs
        """
        record_ids = []
        
        for record in records:
            try:
                record_data = self._build_memory_record(record, context)
                
                doc = frappe.get_doc(record_data)
                doc.insert(ignore_permissions=True)
                record_ids.append(doc.name)
                
            except Exception as e:
                frappe.log_error(f"Failed to persist memory record: {str(e)}", "Capture Service")
        
        return record_ids
    
    def _build_memory_record(
        self,
        record: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build Memory Record document data."""
        import json
        
        return {
            "doctype": "Memory Record",
            "title": record.get("title", "Untitled Memory"),
            "agent": context.get("agent_id") or self.agent_id,
            "conversation": context.get("conversation_id"),
            "run": context.get("run_id"),
            "source_type": context.get("source_type", "conversation"),
            "producer_mode": record.get("producer_mode", "main_agent"),
            "memory_type": record.get("memory_type", "observation"),
            "profile_name": self.config.get("memory_profile"),
            "data_json": json.dumps(record.get("data", {})),
            "summary_text": record.get("summary", ""),
            "raw_context_excerpt": self._extract_context_excerpt(context),
            "scope_type": record.get("scope_type") or self.config.get("scope_type", "conversation"),
            "scope_key": record.get("scope_key") or context.get("scope_key", ""),
            "visibility": self.config.get("visibility", "private"),
            "status": "active",
            "confidence": record.get("confidence", 0.8),
            "importance_score": record.get("importance", 0.5),
            "ttl_days": self.config.get("ttl_days"),
            "created_from_turn_count": context.get("turn_count", 0),
            "tags": record.get("tags", []),
            "metadata_json": json.dumps({
                "capture_service": True,
                "capture_timestamp": datetime.now().isoformat()
            })
        }
    
    def _extract_context_excerpt(self, context: Dict[str, Any], max_length: int = 1000) -> str:
        """Extract text excerpt from conversation context."""
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        if not messages:
            return ""
        
        # Get last few messages
        recent = messages[-5:]
        excerpt_parts = []
        
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                excerpt_parts.append(f"{role}: {content[:200]}")
        
        excerpt = "\n".join(excerpt_parts)
        
        if len(excerpt) > max_length:
            excerpt = excerpt[:max_length] + "..."
        
        return excerpt
    
    def _calculate_latency(self, start_time: datetime) -> int:
        """Calculate elapsed time in milliseconds."""
        elapsed = (datetime.now() - start_time).total_seconds()
        return int(elapsed * 1000)
    
    def get_capture_modes(self) -> List[Dict[str, str]]:
        """
        Get list of available capture modes.
        
        Returns:
            List of mode info dicts with id, name, description
        """
        return [
            {
                "id": "in_prompt",
                "name": "In-Prompt",
                "description": "Zero-latency capture during main agent inference",
                "latency": "zero",
                "producer": "main_agent"
            },
            {
                "id": "post_async",
                "name": "Post-Run Async",
                "description": "Non-blocking async capture via background workers",
                "latency": "zero",
                "producer": "post_run_processor"
            },
            {
                "id": "specialized_agent",
                "name": "Specialized Agent",
                "description": "Dedicated memory extraction agent",
                "latency": "variable",
                "producer": "memory_agent"
            },
            {
                "id": "rule_only",
                "name": "Rule-Only",
                "description": "Deterministic extraction without LLM",
                "latency": "minimal",
                "producer": "rule_engine"
            }
        ]


# Convenience functions for direct use

def capture_memory(
    context: Dict[str, Any],
    agent_id: Optional[str] = None,
    mode: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to capture memory.
    
    Args:
        context: Capture context
        agent_id: Optional agent ID
        mode: Optional capture mode override
        config: Optional configuration
        
    Returns:
        Capture result dict
    """
    service = CaptureService(agent_id=agent_id, config=config)
    return service.capture(context, mode=mode)


def get_capture_service(agent_id: Optional[str] = None) -> CaptureService:
    """
    Get a configured capture service instance.
    
    Args:
        agent_id: Optional agent ID to load policy for
        
    Returns:
        Configured CaptureService instance
    """
    return CaptureService(agent_id=agent_id)
