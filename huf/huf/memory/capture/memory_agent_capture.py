# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Specialized Memory Agent Capture Mode (C3)

Memory agent is a separate Agent record with specialized prompt.
May use cheaper/faster model optimized for extraction.
Receives conversation context + extraction instructions.
Returns structured memory payload.
Can run sync or async depending on trigger configuration.

Capture Mode ID: specialized_agent
Execution Phase: Configurable (sync or async)
Latency Impact: Varies by execution phase
Producer: Dedicated memory agent instance

Key Features:
- Dedicated memory extraction agent
- Optimized prompts for memory extraction
- Configurable execution timing (sync/async)
- Support for full history or summary-only context
- Fallback mechanisms for agent failures
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json


class MemoryAgentCaptureMode:
    """
    Specialized Memory Agent Capture Mode implementation.
    
    Uses a dedicated Agent (configured via Memory Policy) to perform
    memory extraction. This allows:
    - Using a cheaper/faster model for extraction
    - Specialized prompts optimized for memory extraction
    - Independent scaling and configuration
    
    The memory agent receives conversation context and returns
    structured memory records.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize specialized memory agent capture mode.
        
        Args:
            config: Configuration dict with capture settings
                - memory_agent: Required - Name/ID of the memory agent
                - execution_timing: When to run (post_response_sync/post_response_async)
                - pass_full_history: Whether to pass all messages (default: True)
                - pass_summary_only: Pass only summary instead of full context
                - max_context_turns: Maximum turns to include (default: 20)
                - fallback_on_error: How to handle errors (skip/fail/retry)
                - retry_count: Number of retries on failure (default: 1)
                - timeout_seconds: Timeout for agent execution (default: 30)
                - custom_instructions: Additional instructions for memory agent
        """
        self.config = config or {}
        self.mode_type = "specialized_agent"
        self.memory_agent_id = self.config.get("memory_agent")
        
    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate specialized agent capture configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Memory agent is required
        if not self.memory_agent_id:
            errors.append("memory_agent is required for specialized_agent capture mode")
        else:
            # Verify agent exists (if frappe is available)
            try:
                if not frappe.db.exists("Agent", self.memory_agent_id):
                    errors.append(f"Memory agent '{self.memory_agent_id}' does not exist")
            except:
                # frappe might not be available during testing
                pass
        
        # Validate execution timing
        valid_timings = ["post_response_sync", "post_response_async"]
        timing = self.config.get("execution_timing", "post_response_async")
        if timing not in valid_timings:
            errors.append(f"execution_timing must be one of {valid_timings}")
        
        # Validate numeric configs
        if self.config.get("max_context_turns") is not None:
            try:
                turns = int(self.config["max_context_turns"])
                if turns < 1 or turns > 100:
                    errors.append("max_context_turns must be between 1 and 100")
            except (ValueError, TypeError):
                errors.append("max_context_turns must be an integer")
        
        if self.config.get("retry_count") is not None:
            try:
                retries = int(self.config["retry_count"])
                if retries < 0 or retries > 5:
                    errors.append("retry_count must be between 0 and 5")
            except (ValueError, TypeError):
                errors.append("retry_count must be an integer")
        
        return len(errors) == 0, errors
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute specialized memory agent capture.
        
        Args:
            context: Capture context containing:
                - conversation: Dict with messages, metadata
                - run: Dict with run details
                - agent_response: String agent response
                - agent_id: Source agent ID
                - user_id: User ID
                - conversation_id: Conversation ID
                - run_id: Run ID
                - conversation_summary: Optional pre-computed summary
                - turn_count: Number of turns in conversation
                
        Returns:
            Dict with capture results:
            - records_created: Number of records extracted
            - records_updated: Number of records updated
            - validation_errors: List of validation errors
            - skipped: Whether capture was skipped
            - reason: Reason for skipping
            - payload: Extracted memory records
            - agent_run_id: ID of the memory agent run
            - latency_ms: Processing time
            - async: Whether execution was async
            - job_name: Background job name (if async)
        """
        start_time = datetime.now()
        
        # Validate configuration
        is_valid, validation_errors = self.validate()
        if not is_valid:
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": validation_errors,
                "skipped": True,
                "reason": "Configuration validation failed",
                "payload": {},
                "latency_ms": self._calculate_latency(start_time)
            }
        
        execution_timing = self.config.get("execution_timing", "post_response_async")
        
        # Route to appropriate execution method
        if execution_timing == "post_response_async":
            return self._execute_async(context, start_time)
        else:
            return self._execute_sync(context, start_time)
    
    def _execute_sync(
        self,
        context: Dict[str, Any],
        start_time: datetime
    ) -> Dict[str, Any]:
        """
        Execute memory agent synchronously.
        
        Args:
            context: Capture context
            start_time: Execution start time
            
        Returns:
            Capture result dict
        """
        retry_count = self.config.get("retry_count", 1)
        last_error = None
        
        for attempt in range(retry_count + 1):
            try:
                result = self._run_memory_agent(context)
                result["latency_ms"] = self._calculate_latency(start_time)
                result["async"] = False
                return result
                
            except Exception as e:
                last_error = e
                frappe.logger().warning(
                    f"Memory agent attempt {attempt + 1} failed: {e}"
                )
                
                if attempt < retry_count:
                    import time
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        # All retries failed
        fallback = self.config.get("fallback_on_error", "skip")
        
        if fallback == "fail":
            raise last_error
        
        # Log error and return skip result
        frappe.log_error(
            f"Memory agent capture failed after {retry_count + 1} attempts: {last_error}",
            "Memory Agent Capture"
        )
        
        return {
            "records_created": 0,
            "records_updated": 0,
            "validation_errors": [str(last_error)],
            "skipped": True,
            "reason": f"Memory agent failed: {str(last_error)}",
            "payload": {},
            "latency_ms": self._calculate_latency(start_time),
            "async": False
        }
    
    def _execute_async(
        self,
        context: Dict[str, Any],
        start_time: datetime
    ) -> Dict[str, Any]:
        """
        Execute memory agent asynchronously via background job.
        
        Args:
            context: Capture context
            start_time: Execution start time
            
        Returns:
            Capture result dict with job info
        """
        conversation_id = context.get("conversation_id", "unknown")
        run_id = context.get("run_id", "unknown")
        
        # Prepare context snapshot for background processing
        snapshot = self._prepare_context_snapshot(context)
        
        try:
            job_name = f"memory_agent_capture_{conversation_id}_{int(datetime.now().timestamp())}"
            
            # Enqueue background job
            frappe.enqueue(
                method="huf.memory.capture.memory_agent_capture.process_memory_agent_job",
                queue=self.config.get("queue_name", "memory_capture"),
                job_name=job_name,
                memory_agent_id=self.memory_agent_id,
                snapshot=snapshot,
                config=self.config,
                timeout=self.config.get("timeout_seconds", 300),
                retry_count=self.config.get("retry_count", 1)
            )
            
            return {
                "records_created": 0,  # Created asynchronously
                "records_updated": 0,
                "validation_errors": [],
                "skipped": False,
                "job_enqueued": True,
                "job_name": job_name,
                "payload": {},
                "latency_ms": self._calculate_latency(start_time),
                "async": True
            }
            
        except Exception as e:
            frappe.log_error(f"Failed to enqueue memory agent job: {str(e)}", "Memory Agent Capture")
            
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": [str(e)],
                "skipped": True,
                "reason": f"Enqueue failed: {str(e)}",
                "payload": {},
                "latency_ms": self._calculate_latency(start_time),
                "async": True
            }
    
    def _run_memory_agent(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the specialized memory agent.
        
        Args:
            context: Capture context
            
        Returns:
            Capture result dict
        """
        # Prepare prompt for memory agent
        prompt = self._prepare_agent_prompt(context)
        
        # Run the agent
        try:
            # Import here to avoid circular dependencies
            from huf.ai.agent_integration import run_agent_sync
            
            result = run_agent_sync(
                agent_name=self.memory_agent_id,
                prompt=prompt,
                channel_id=f"memory_capture_{context.get('conversation_id', 'unknown')}",
                timeout=self.config.get("timeout_seconds", 30)
            )
            
            agent_run_id = result.get("agent_run_id")
            response_text = result.get("response", "{}")
            
            # Parse JSON response
            try:
                response_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                response_data = self._extract_json_from_markdown(response_text)
            
            # Handle different response formats
            if "memory_update" in response_data:
                records = response_data["memory_update"].get("records", [])
            elif "records" in response_data:
                records = response_data["records"]
            elif isinstance(response_data, list):
                records = response_data
            else:
                # Single record
                records = [response_data] if response_data else []
            
            # Validate and normalize records
            validated_records = []
            errors = []
            
            for i, record in enumerate(records):
                record_errors = self._validate_record(record)
                if record_errors:
                    errors.extend([f"Record {i}: {e}" for e in record_errors])
                else:
                    normalized = self._normalize_record(record, context)
                    validated_records.append(normalized)
            
            return {
                "records_created": len(validated_records),
                "records_updated": 0,
                "validation_errors": errors,
                "skipped": len(validated_records) == 0,
                "reason": "No valid records extracted" if not validated_records else None,
                "payload": {"records": validated_records},
                "agent_run_id": agent_run_id
            }
            
        except ImportError:
            # Fallback if agent_integration is not available
            frappe.logger().warning("huf.ai.agent_integration not available, using mock response")
            return self._mock_agent_execution(context)
            
        except Exception as e:
            frappe.log_error(f"Memory agent execution failed: {str(e)}", "Memory Agent Capture")
            raise
    
    def _prepare_agent_prompt(self, context: Dict[str, Any]) -> str:
        """
        Prepare the prompt for the specialized memory agent.
        
        Args:
            context: Capture context
            
        Returns:
            Formatted prompt string
        """
        # Get conversation context
        pass_full_history = self.config.get("pass_full_history", True)
        pass_summary_only = self.config.get("pass_summary_only", False)
        max_turns = self.config.get("max_context_turns", 20)
        
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        if pass_summary_only:
            conversation_text = context.get("conversation_summary", "")
            if not conversation_text:
                # Generate simple summary if not provided
                conversation_text = self._generate_simple_summary(messages)
        elif pass_full_history:
            # Include all messages up to max_turns
            if len(messages) > max_turns:
                messages = messages[-max_turns:]
            
            conversation_text = self._format_messages_for_agent(messages)
        else:
            # Recent messages only
            recent_messages = messages[-max_turns:] if len(messages) > max_turns else messages
            conversation_text = self._format_messages_for_agent(recent_messages)
        
        # Get custom instructions
        custom_instructions = self.config.get("custom_instructions", "")
        
        prompt = f"""You are a specialized memory extraction agent. Your task is to analyze conversation context and extract structured memory records.

## Conversation Context

{conversation_text}

## Extraction Instructions

Analyze the conversation and extract any information worth remembering for future interactions. Focus on:

1. **User Profile Information**: Name, role, preferences, background
2. **Facts**: Factual information shared by the user
3. **Preferences**: Explicit likes, dislikes, choices
4. **Plans & Goals**: Future plans, commitments, objectives
5. **Insights**: Patterns, observations, conclusions
6. **Domain Objects**: Structured data (addresses, configurations, etc.)

## Output Format

Return a JSON object with the following structure:

```json
{{
  "memory_update": {{
    "records": [
      {{
        "title": "Brief descriptive title",
        "memory_type": "profile|preference|fact|plan|observation|insight|domain_object",
        "data": {{...}},
        "confidence": 0.0-1.0,
        "importance": 0.0-1.0,
        "summary": "Optional human-readable summary",
        "tags": ["tag1", "tag2"]
      }}
    ]
  }}
}}
```

## Guidelines

- Only extract information with confidence ≥ 0.7
- Assign importance based on long-term value
- Include only factual, reusable information
- Omit transient or context-specific details
- Return empty records array if nothing is worth capturing

{custom_instructions}

Extract memories now."""
        
        return prompt
    
    def _prepare_context_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare a snapshot of context for background processing.
        
        Args:
            context: Full capture context
            
        Returns:
            Serializable context snapshot
        """
        max_turns = self.config.get("max_context_turns", 20)
        
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        # Limit context to recent messages
        if len(messages) > max_turns:
            messages = messages[-max_turns:]
        
        return {
            "agent_id": context.get("agent_id"),
            "user_id": context.get("user_id"),
            "conversation_id": context.get("conversation_id"),
            "run_id": context.get("run_id"),
            "messages": messages,
            "agent_response": context.get("agent_response"),
            "conversation_summary": context.get("conversation_summary"),
            "turn_count": context.get("turn_count", len(messages)),
            "captured_at": datetime.now().isoformat()
        }
    
    def _format_messages_for_agent(self, messages: List[Dict]) -> str:
        """Format messages for memory agent consumption."""
        formatted = []
        
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if content:
                # Truncate very long messages
                if len(content) > 1000:
                    content = content[:997] + "..."
                
                formatted.append(f"[{role.upper()}]\n{content}\n")
        
        return "\n".join(formatted)
    
    def _generate_simple_summary(self, messages: List[Dict]) -> str:
        """Generate a simple summary from messages."""
        # Simple extraction of key points
        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        assistant_msgs = [m.get("content", "") for m in messages if m.get("role") == "assistant"]
        
        summary_parts = []
        
        if user_msgs:
            summary_parts.append("User messages:\n" + "\n".join(user_msgs[-3:]))
        
        if assistant_msgs:
            summary_parts.append("Assistant responses:\n" + "\n".join(assistant_msgs[-3:]))
        
        return "\n\n".join(summary_parts)
    
    def _extract_json_from_markdown(self, text: str) -> Dict[str, Any]:
        """Extract JSON from markdown code blocks."""
        import re
        
        # Try to find JSON in code blocks
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        # Try to find JSON-like structure
        try:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
        
        return {"raw_response": text}
    
    def _validate_record(self, record: Dict[str, Any]) -> List[str]:
        """Validate a memory record."""
        errors = []
        
        if not record.get("title"):
            errors.append("Missing required field: title")
        
        if not record.get("memory_type"):
            errors.append("Missing required field: memory_type")
        
        # Validate confidence
        confidence = record.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
                if confidence < 0 or confidence > 1:
                    errors.append("confidence must be between 0.0 and 1.0")
            except (ValueError, TypeError):
                errors.append("confidence must be a number")
        
        return errors
    
    def _normalize_record(
        self,
        record: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize a memory record with defaults."""
        return {
            "title": record.get("title", ""),
            "memory_type": record.get("memory_type", "observation"),
            "data": record.get("data", {}),
            "confidence": record.get("confidence", 0.8),
            "importance": record.get("importance", 0.5),
            "summary": record.get("summary", ""),
            "tags": record.get("tags", []),
            "scope_type": record.get("scope_type") or context.get("scope_type", "conversation"),
            "scope_key": record.get("scope_key") or context.get("scope_key", ""),
            "source_type": "conversation",
            "producer_mode": "memory_agent"
        }
    
    def _mock_agent_execution(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Mock execution for testing when agent integration is unavailable."""
        return {
            "records_created": 0,
            "records_updated": 0,
            "validation_errors": [],
            "skipped": True,
            "reason": "Mock mode - agent integration not available",
            "payload": {},
            "mock": True
        }
    
    def _calculate_latency(self, start_time: datetime) -> int:
        """Calculate elapsed time in milliseconds."""
        elapsed = (datetime.now() - start_time).total_seconds()
        return int(elapsed * 1000)
    
    def get_latency_impact(self) -> str:
        """Return latency impact classification."""
        execution_timing = self.config.get("execution_timing", "post_response_async")
        if execution_timing == "post_response_async":
            return "zero"
        return "variable"
    
    def get_producer(self) -> str:
        """Return the producer type for this capture mode."""
        return self.memory_agent_id or "memory_agent"


def process_memory_agent_job(
    memory_agent_id: str,
    snapshot: Dict[str, Any],
    config: Dict[str, Any]
):
    """
    Background job handler for memory agent capture.
    
    Args:
        memory_agent_id: ID of the memory agent to run
        snapshot: Context snapshot
        config: Capture configuration
    """
    try:
        # Reconstruct context from snapshot
        context = {
            "agent_id": snapshot.get("agent_id"),
            "user_id": snapshot.get("user_id"),
            "conversation_id": snapshot.get("conversation_id"),
            "run_id": snapshot.get("run_id"),
            "conversation": {"messages": snapshot.get("messages", [])},
            "agent_response": snapshot.get("agent_response"),
            "conversation_summary": snapshot.get("conversation_summary"),
            "turn_count": snapshot.get("turn_count", 0)
        }
        
        # Create capture mode and execute synchronously
        capture_mode = MemoryAgentCaptureMode({**config, "memory_agent": memory_agent_id})
        result = capture_mode._run_memory_agent(context)
        
        frappe.logger().info(
            f"Memory agent background job completed for conversation "
            f"{context['conversation_id']}: {result['records_created']} records"
        )
        
        return result
        
    except Exception as e:
        frappe.log_error(
            f"Memory agent background job failed: {str(e)}",
            "Memory Agent Capture"
        )
        raise


def create_memory_agent_capture(config: Dict[str, Any]) -> MemoryAgentCaptureMode:
    """
    Factory function to create a MemoryAgentCaptureMode instance.
    
    Args:
        config: Configuration dict with memory_agent and other settings
        
    Returns:
        MemoryAgentCaptureMode instance
    """
    return MemoryAgentCaptureMode(config)
