# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Rule-Only Capture Mode (C4)

Deterministic memory extraction without LLM inference.
Memory fields populated from:
- Exact context values (user_id, timestamp, state flags)
- Regex/template extractions
- Tool call outputs
- System event payloads
- JSON Path or Jinja2 template mapping

Direct commit to memory record with minimal latency.

Capture Mode ID: rule_only
Execution Phase: Deterministic (synchronous)
Latency Impact: Minimal (no LLM call)
Producer: rule_engine
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union
import re
from datetime import datetime


class RuleOnlyCaptureMode:
    """
    Rule-Only Capture Mode implementation.
    
    Uses deterministic rules to extract memory fields from context
    without requiring any LLM inference. Supports:
    - Static value assignment
    - Context path extraction
    - Regex pattern matching
    - Tool output capture
    - Computed fields
    """
    
    # Supported rule types
    RULE_TYPES = ["static", "context", "regex", "jsonpath", "tool", "computed", "jinja"]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize rule-only capture mode.
        
        Args:
            config: Configuration dict with 'rules' list
        """
        self.config = config or {}
        self.rules = self.config.get("rules", [])
        self.mode_type = "rule_only"
        
    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate rule configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        if not self.rules:
            errors.append("No rules configured for rule-only capture mode")
            return False, errors
        
        for i, rule in enumerate(self.rules):
            rule_errors = self._validate_rule(rule, i)
            errors.extend(rule_errors)
        
        return len(errors) == 0, errors
    
    def _validate_rule(self, rule: Dict[str, Any], index: int) -> List[str]:
        """Validate a single rule configuration."""
        errors = []
        rule_name = rule.get("field", f"rule_{index}")
        
        # Check required fields
        if not rule.get("field"):
            errors.append(f"Rule {index}: 'field' is required")
        
        rule_type = rule.get("source") or rule.get("type")
        if not rule_type:
            errors.append(f"Rule {rule_name}: 'source' or 'type' is required")
        elif rule_type not in self.RULE_TYPES:
            errors.append(f"Rule {rule_name}: Unknown rule type '{rule_type}'")
        
        # Type-specific validation
        if rule_type == "static" and "value" not in rule:
            errors.append(f"Rule {rule_name}: 'value' required for static rule")
        
        if rule_type == "context" and not rule.get("path"):
            errors.append(f"Rule {rule_name}: 'path' required for context rule")
        
        if rule_type == "regex":
            if not rule.get("pattern"):
                errors.append(f"Rule {rule_name}: 'pattern' required for regex rule")
            else:
                # Validate regex pattern
                try:
                    re.compile(rule["pattern"])
                except re.error as e:
                    errors.append(f"Rule {rule_name}: Invalid regex pattern: {e}")
        
        if rule_type == "jsonpath":
            if not rule.get("path"):
                errors.append(f"Rule {rule_name}: 'path' required for jsonpath rule")
        
        if rule_type == "tool":
            if not rule.get("tool_name"):
                errors.append(f"Rule {rule_name}: 'tool_name' required for tool rule")
        
        if rule_type == "computed":
            if not rule.get("formula"):
                errors.append(f"Rule {rule_name}: 'formula' required for computed rule")
        
        return errors
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute rule-only capture against the provided context.
        
        Args:
            context: Capture context containing conversation, run, tool outputs, etc.
                Expected keys:
                - conversation: Dict with messages, metadata
                - run: Dict with run details
                - tool_outputs: List of tool execution results
                - agent_response: String of agent's response
                - agent_id: String agent identifier
                - user_id: String user identifier
                - conversation_id: String conversation identifier
                - run_id: String run identifier
                
        Returns:
            Dict with capture results:
            - records_created: Number of records that would be created
            - records_updated: Number of records updated
            - validation_errors: List of any errors during extraction
            - skipped: Whether capture was skipped
            - reason: Reason for skipping (if applicable)
            - payload: Extracted memory data dict
            - rule_results: Dict of individual rule execution results
        """
        start_time = datetime.now()
        extracted = {}
        errors = []
        rule_results = {}
        
        # Validate rules before execution
        is_valid, validation_errors = self.validate()
        if not is_valid:
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": validation_errors,
                "skipped": True,
                "reason": "Rule validation failed",
                "payload": {},
                "rule_results": {}
            }
        
        # Execute each rule
        for rule in self.rules:
            field_name = rule.get("field")
            rule_type = rule.get("source") or rule.get("type")
            
            try:
                value = self._execute_rule(rule, context)
                
                if value is not None:
                    extracted[field_name] = value
                    rule_results[field_name] = {
                        "success": True,
                        "value": value,
                        "rule_type": rule_type
                    }
                elif rule.get("required"):
                    errors.append(f"Required field '{field_name}' could not be extracted")
                    rule_results[field_name] = {
                        "success": False,
                        "error": "Required field extraction failed",
                        "rule_type": rule_type
                    }
                else:
                    rule_results[field_name] = {
                        "success": True,
                        "value": None,
                        "skipped": True,
                        "rule_type": rule_type
                    }
                    
            except Exception as e:
                error_msg = f"Rule '{field_name}' failed: {str(e)}"
                errors.append(error_msg)
                rule_results[field_name] = {
                    "success": False,
                    "error": str(e),
                    "rule_type": rule_type
                }
                
                if rule.get("required"):
                    frappe.log_error(error_msg, "Rule-Only Capture")
        
        # Calculate latency
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "records_created": 1 if extracted else 0,
            "records_updated": 0,
            "validation_errors": errors,
            "skipped": not extracted,
            "reason": "No fields extracted" if not extracted else None,
            "payload": extracted,
            "rule_results": rule_results,
            "latency_ms": latency_ms,
            "mode_type": self.mode_type
        }
    
    def _execute_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a single extraction rule.
        
        Args:
            rule: Rule configuration dict
            context: Capture context
            
        Returns:
            Extracted value or None
        """
        rule_type = rule.get("source") or rule.get("type")
        
        handlers = {
            "static": self._execute_static_rule,
            "context": self._execute_context_rule,
            "regex": self._execute_regex_rule,
            "jsonpath": self._execute_jsonpath_rule,
            "tool": self._execute_tool_rule,
            "computed": self._execute_computed_rule,
            "jinja": self._execute_jinja_rule
        }
        
        handler = handlers.get(rule_type)
        if not handler:
            raise ValueError(f"Unknown rule type: {rule_type}")
        
        return handler(rule, context)
    
    def _execute_static_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute static value assignment rule.
        
        Supports template variables:
        - {{ now() }} - Current timestamp
        - {{ today() }} - Current date
        - {{ user }} - Current user
        """
        value = rule.get("value")
        
        if not isinstance(value, str):
            return value
        
        # Handle template variables
        if "{{" in value:
            from frappe.utils import now, today
            
            replacements = {
                "{{ now() }}": now(),
                "{{ today() }}": today(),
                "{{ user }}": frappe.session.user,
                "{{ timestamp }}": datetime.now().isoformat()
            }
            
            for template, replacement in replacements.items():
                value = value.replace(template, replacement)
        
        return value
    
    def _execute_context_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute context path extraction rule.
        
        Path format: dot notation (e.g., "conversation.messages.0.content")
        """
        path = rule.get("path", "")
        default = rule.get("default")
        
        if not path:
            return default
        
        value = self._get_nested_value(context, path)
        return value if value is not None else default
    
    def _execute_regex_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute regex pattern matching rule.
        
        Args:
            rule: Rule with 'pattern', 'source_text', 'on_match', 'group_index'
            context: Capture context
        """
        pattern = rule.get("pattern", "")
        source_text_key = rule.get("source_text", "user_messages")
        on_match = rule.get("on_match")
        group_index = rule.get("group_index", 1)
        
        # Get text to match against
        text = self._get_text_for_regex(context, source_text_key)
        
        if not text:
            return None
        
        # Perform regex match
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        
        if not match:
            return None
        
        # Handle on_match value
        if on_match is not None:
            return on_match
        
        # Return captured group or full match
        if match.groups():
            if isinstance(group_index, int) and group_index <= len(match.groups()):
                return match.group(group_index)
            return match.group(1)
        
        return match.group(0)
    
    def _execute_jsonpath_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute JSONPath extraction rule.
        
        Uses simplified JSONPath-like syntax for nested value extraction.
        """
        path = rule.get("path", "")
        source = rule.get("source", "context")  # context, tool_output, etc.
        default = rule.get("default")
        
        # Get source data
        if source == "context":
            data = context
        elif source.startswith("tool_output."):
            tool_name = source.replace("tool_output.", "")
            data = self._get_tool_output(context, tool_name)
        else:
            data = context.get(source, {})
        
        if not data:
            return default
        
        # Execute JSONPath-like extraction
        value = self._get_nested_value(data, path)
        return value if value is not None else default
    
    def _execute_tool_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute tool output extraction rule.
        
        Extracts values from tool call outputs.
        """
        tool_name = rule.get("tool_name")
        output_path = rule.get("path", "")
        default = rule.get("default")
        match_by = rule.get("match_by")  # Optional: match by additional criteria
        
        tool_outputs = context.get("tool_outputs", [])
        
        for output in tool_outputs:
            if output.get("tool") == tool_name or output.get("tool_name") == tool_name:
                # Check match criteria if specified
                if match_by:
                    match_field = match_by.get("field")
                    match_value = match_by.get("value")
                    if match_field and output.get(match_field) != match_value:
                        continue
                
                # Extract value from output
                if output_path:
                    value = self._get_nested_value(output, output_path)
                    if value is not None:
                        return value
                else:
                    return output.get("output") or output.get("result")
        
        return default
    
    def _execute_computed_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute computed field rule.
        
        Built-in formulas:
        - turn_count: Number of messages in conversation
        - message_count: Alias for turn_count
        - user_message_count: Count of user messages
        - assistant_message_count: Count of assistant messages
        - duration_seconds: Calculate duration from timestamps
        - word_count: Count words in messages
        - char_count: Count characters in messages
        """
        formula = rule.get("formula", "")
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        if formula == "turn_count" or formula == "message_count":
            return len(messages)
        
        elif formula == "user_message_count":
            return sum(1 for m in messages if m.get("role") == "user")
        
        elif formula == "assistant_message_count":
            return sum(1 for m in messages if m.get("role") == "assistant")
        
        elif formula == "duration_seconds":
            start_time = context.get("start_time")
            end_time = context.get("end_time") or datetime.now().isoformat()
            
            if start_time and end_time:
                try:
                    start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    return int((end - start).total_seconds())
                except:
                    return 0
            return 0
        
        elif formula == "word_count":
            text = self._get_all_message_text(messages)
            return len(text.split())
        
        elif formula == "char_count":
            text = self._get_all_message_text(messages)
            return len(text)
        
        elif formula == "timestamp":
            return datetime.now().isoformat()
        
        elif formula == "unix_timestamp":
            return int(datetime.now().timestamp())
        
        else:
            raise ValueError(f"Unknown formula: {formula}")
    
    def _execute_jinja_rule(self, rule: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute Jinja2 template rule.
        
        Renders a Jinja2 template with context variables.
        """
        template_str = rule.get("template", "")
        
        if not template_str:
            return None
        
        try:
            from jinja2 import Template
            
            template = Template(template_str)
            
            # Build template context
            template_context = {
                "context": context,
                "conversation": context.get("conversation", {}),
                "run": context.get("run", {}),
                "agent_id": context.get("agent_id"),
                "user_id": context.get("user_id"),
                "conversation_id": context.get("conversation_id"),
                "run_id": context.get("run_id"),
                "now": datetime.now(),
                "frappe": frappe
            }
            
            return template.render(**template_context)
            
        except Exception as e:
            raise ValueError(f"Jinja template error: {e}")
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """
        Get a nested value using dot notation.
        
        Supports:
        - Simple paths: "user.name"
        - Array indices: "messages.0.content"
        - Wildcards: "messages.*.content" (returns list)
        """
        if not path:
            return data
        
        parts = path.split(".")
        current = data
        
        for i, part in enumerate(parts):
            if current is None:
                return None
            
            # Handle array indexing
            if part.isdigit():
                idx = int(part)
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return None
            # Handle wildcard for arrays
            elif part == "*":
                if isinstance(current, list):
                    remaining_path = ".".join(parts[i+1:])
                    return [self._get_nested_value(item, remaining_path) for item in current]
                else:
                    return None
            # Handle dict key
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        
        return current
    
    def _get_text_for_regex(self, context: Dict[str, Any], source: str) -> str:
        """
        Get text to apply regex against based on source specification.
        
        Sources:
        - user_messages: All user message contents
        - assistant_messages: All assistant message contents
        - all_messages: All messages with role prefixes
        - last_user_message: Most recent user message
        - last_assistant_message: Most recent assistant message
        - last_message: Most recent message regardless of role
        - agent_response: The agent's response text
        """
        conversation = context.get("conversation", {})
        messages = conversation.get("messages", [])
        
        if source == "user_messages":
            return "\n".join([
                msg.get("content", "")
                for msg in messages
                if msg.get("role") == "user"
            ])
        
        elif source == "assistant_messages":
            return "\n".join([
                msg.get("content", "")
                for msg in messages
                if msg.get("role") == "assistant"
            ])
        
        elif source == "all_messages":
            return "\n".join([
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                for msg in messages
            ])
        
        elif source == "last_user_message":
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    return msg.get("content", "")
            return ""
        
        elif source == "last_assistant_message":
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    return msg.get("content", "")
            return ""
        
        elif source == "last_message":
            if messages:
                return messages[-1].get("content", "")
            return ""
        
        elif source == "agent_response":
            return context.get("agent_response", "")
        
        else:
            # Try to get from context directly
            return context.get(source, "")
    
    def _get_tool_output(self, context: Dict[str, Any], tool_name: str) -> Optional[Dict]:
        """Get output for a specific tool from context."""
        tool_outputs = context.get("tool_outputs", [])
        
        for output in tool_outputs:
            if output.get("tool") == tool_name or output.get("tool_name") == tool_name:
                return output.get("output") or output.get("result") or output
        
        return None
    
    def _get_all_message_text(self, messages: List[Dict]) -> str:
        """Get concatenated text from all messages."""
        return " ".join([
            msg.get("content", "")
            for msg in messages
            if msg.get("content")
        ])
    
    def get_latency_impact(self) -> str:
        """Return latency impact classification."""
        return "minimal"
    
    def get_producer(self) -> str:
        """Return the producer type for this capture mode."""
        return "rule_engine"


def create_rule_only_capture(config: Dict[str, Any]) -> RuleOnlyCaptureMode:
    """
    Factory function to create a RuleOnlyCaptureMode instance.
    
    Args:
        config: Configuration dict with 'rules' list
        
    Returns:
        RuleOnlyCaptureMode instance
    """
    return RuleOnlyCaptureMode(config)


# Example rule configurations for documentation
EXAMPLE_RULES = {
    "user_id_capture": {
        "field": "user_identifier",
        "source": "context",
        "path": "user_id",
        "required": True
    },
    "timestamp_capture": {
        "field": "captured_at",
        "source": "static",
        "value": "{{ now() }}"
    },
    "email_extraction": {
        "field": "user_email",
        "source": "regex",
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "source_text": "user_messages",
        "required": False
    },
    "turn_count": {
        "field": "conversation_length",
        "source": "computed",
        "formula": "turn_count"
    },
    "tool_result": {
        "field": "search_results",
        "source": "tool",
        "tool_name": "web_search",
        "path": "results.0.title"
    }
}
