# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
In-Prompt Capture Mode (C1)

Memory instructions are prepended to the main agent system prompt.
Agent outputs memory updates as part of its JSON response structure.
Memory fields are extracted from the response and committed synchronously.
Schema validation occurs post-response before write.

Capture Mode ID: in_prompt
Execution Phase: During main agent inference (zero additional latency)
Latency Impact: Zero (part of main request)
Producer: main_agent

Key Features:
- Memory capture prompt injection into system prompt
- Structured JSON response format with memory_update field
- Synchronous extraction and validation
- Schema-based validation with type checking
- Support for multiple memory records per response
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json


class InPromptCaptureMode:
    """
    In-Prompt Capture Mode implementation.
    
    Integrates memory capture instructions directly into the agent's
    system prompt. The agent includes memory updates in its structured
    response, which are then extracted and persisted synchronously.
    
    This mode has zero additional latency because the memory extraction
    happens as part of the main LLM inference.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize in-prompt capture mode.
        
        Args:
            config: Configuration dict with capture settings
                - schema_json: JSON schema for validation
                - require_json_schema_match: Enforce strict schema validation
                - allow_multiple_records: Allow multiple memory records per response
                - memory_prompt_template: Custom prompt template
                - max_memory_items: Maximum memory items per response
                - default_memory_type: Default type if not specified
        """
        self.config = config or {}
        self.mode_type = "in_prompt"
        
    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate in-prompt capture configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Validate schema if provided
        schema = self.config.get("schema_json")
        if schema and not isinstance(schema, dict):
            errors.append("schema_json must be a dictionary")
        
        # Validate max_memory_items
        max_items = self.config.get("max_memory_items")
        if max_items is not None:
            try:
                max_items = int(max_items)
                if max_items < 1 or max_items > 100:
                    errors.append("max_memory_items must be between 1 and 100")
            except (ValueError, TypeError):
                errors.append("max_memory_items must be an integer")
        
        return len(errors) == 0, errors
    
    def build_memory_instruction_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Build the memory instruction prompt to inject into system prompt.
        
        This prompt instructs the agent on how to include memory updates
        in its structured response.
        
        Args:
            context: Optional context for template variables
            
        Returns:
            Memory instruction prompt string
        """
        template = self.config.get("memory_prompt_template")
        
        if template:
            return self._render_template(template, context)
        
        schema = self.config.get("schema_json", {})
        schema_description = self._format_schema_for_prompt(schema)
        
        default_memory_type = self.config.get("default_memory_type", "observation")
        max_items = self.config.get("max_memory_items", 5)
        
        prompt = f"""## Memory Capture Instructions

As you respond to the user, identify any information worth remembering for future conversations. This includes:
- User preferences, facts about the user, or their context
- Important decisions, plans, or commitments made
- Domain knowledge shared that may be useful later
- Corrections or clarifications to previous understanding

### Response Format

Your response must include a `memory_update` field containing memory records to save. Structure:

```json
{{
  "response": "Your natural language response to the user",
  "memory_update": {{
    "has_updates": true,
    "records": [
      {{
        "title": "Brief descriptive title",
        "memory_type": "{default_memory_type}",
        "data": {{...}},
        "confidence": 0.9,
        "importance": 0.8,
        "summary": "Optional human-readable summary"
      }}
    ]
  }}
}}
```

### Memory Types

Choose the appropriate type for each memory:
- `profile` - User profile information (name, role, preferences)
- `preference` - Explicit preferences stated by the user
- `fact` - Factual information about the user or context
- `plan` - Future plans, goals, or commitments
- `observation` - Observations about patterns or behaviors
- `insight` - Derived insights or conclusions
- `domain_object` - Structured domain data (addresses, configs, etc.)

### Guidelines

1. Only capture information with confidence ≥ 0.7
2. Assign importance based on long-term value (0.0-1.0)
3. Keep data structured and concise
4. Use `has_updates: false` if nothing is worth capturing
5. Maximum {max_items} memory records per response
{schema_description}

### Example

```json
{{
  "response": "I'll help you plan your trip to Tokyo!",
  "memory_update": {{
    "has_updates": true,
    "records": [
      {{
        "title": "User Planning Tokyo Trip",
        "memory_type": "plan",
        "data": {{"destination": "Tokyo", "status": "planning"}},
        "confidence": 0.95,
        "importance": 0.9
      }}
    ]
  }}
}}
```
"""
        return prompt
    
    def execute(
        self,
        response_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute in-prompt capture from agent response.
        
        Extracts memory updates from the structured response and
        validates them against the configured schema.
        
        Args:
            response_data: The structured response from the agent
                Expected format:
                {
                    "response": "...",
                    "memory_update": {
                        "has_updates": true/false,
                        "records": [...]
                    }
                }
            context: Optional capture context for metadata
            
        Returns:
            Dict with capture results:
            - records_created: Number of valid records extracted
            - records_updated: Number of records updated (usually 0 for in-prompt)
            - validation_errors: List of validation errors
            - skipped: Whether capture was skipped
            - reason: Reason for skipping
            - payload: Extracted and validated memory records
            - latency_ms: Processing time in milliseconds
        """
        start_time = datetime.now()
        context = context or {}
        
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
        
        # Extract memory update from response
        memory_update = response_data.get("memory_update")
        
        if not memory_update:
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": [],
                "skipped": True,
                "reason": "No memory_update field in response",
                "payload": {},
                "latency_ms": self._calculate_latency(start_time)
            }
        
        # Check if updates are indicated
        if not memory_update.get("has_updates", False):
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": [],
                "skipped": True,
                "reason": "has_updates is false",
                "payload": {},
                "latency_ms": self._calculate_latency(start_time)
            }
        
        # Get records list
        records = memory_update.get("records", [])
        
        if not records:
            return {
                "records_created": 0,
                "records_updated": 0,
                "validation_errors": [],
                "skipped": True,
                "reason": "No records in memory_update",
                "payload": {},
                "latency_ms": self._calculate_latency(start_time)
            }
        
        # Check max items limit
        max_items = self.config.get("max_memory_items", 5)
        if len(records) > max_items:
            records = records[:max_items]
            frappe.logger().warning(
                f"In-prompt capture: Truncated {len(records)} records to max {max_items}"
            )
        
        # Validate each record
        validated_records = []
        errors = []
        
        schema = self.config.get("schema_json", {})
        require_schema = self.config.get("require_json_schema_match", False)
        
        for i, record in enumerate(records):
            record_errors = self._validate_record(record, schema, require_schema)
            
            if record_errors:
                errors.extend([f"Record {i}: {e}" for e in record_errors])
                if require_schema:
                    continue
            
            # Normalize record
            normalized = self._normalize_record(record, context)
            validated_records.append(normalized)
        
        # Build result
        latency_ms = self._calculate_latency(start_time)
        
        return {
            "records_created": len(validated_records),
            "records_updated": 0,
            "validation_errors": errors,
            "skipped": len(validated_records) == 0,
            "reason": "All records failed validation" if not validated_records else None,
            "payload": {
                "records": validated_records
            },
            "latency_ms": latency_ms,
            "mode_type": self.mode_type
        }
    
    def _validate_record(
        self,
        record: Dict[str, Any],
        schema: Dict[str, Any],
        require_schema: bool
    ) -> List[str]:
        """
        Validate a single memory record.
        
        Args:
            record: Memory record dict
            schema: JSON schema for validation
            require_schema: Whether to enforce strict schema
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Check required fields
        if not record.get("title"):
            errors.append("Missing required field: title")
        
        if not record.get("memory_type"):
            errors.append("Missing required field: memory_type")
        
        # Validate memory_type value
        valid_types = [
            "profile", "session_state", "preference", "fact",
            "plan", "observation", "insight", "domain_object", "custom"
        ]
        if record.get("memory_type") and record["memory_type"] not in valid_types:
            errors.append(f"Invalid memory_type: {record['memory_type']}")
        
        # Validate confidence range
        confidence = record.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
                if confidence < 0 or confidence > 1:
                    errors.append("confidence must be between 0.0 and 1.0")
            except (ValueError, TypeError):
                errors.append("confidence must be a number")
        
        # Validate importance range
        importance = record.get("importance")
        if importance is not None:
            try:
                importance = float(importance)
                if importance < 0 or importance > 1:
                    errors.append("importance must be between 0.0 and 1.0")
            except (ValueError, TypeError):
                errors.append("importance must be a number")
        
        # Schema validation
        if schema and require_schema:
            schema_errors = self._validate_schema(record, schema)
            errors.extend(schema_errors)
        
        return errors
    
    def _validate_schema(self, record: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """
        Validate record against JSON schema.
        
        Args:
            record: Memory record to validate
            schema: JSON schema dict
            
        Returns:
            List of validation errors
        """
        errors = []
        
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        # Check required fields
        for field in required:
            if field not in record:
                errors.append(f"Schema requires field: {field}")
        
        # Validate field types
        for field, value in record.items():
            if field in properties:
                prop_def = properties[field]
                expected_type = prop_def.get("type")
                
                if expected_type and not self._check_type(value, expected_type):
                    errors.append(
                        f"Field '{field}' has wrong type. Expected {expected_type}"
                    )
        
        return errors
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON schema type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
        }
        
        expected = type_map.get(expected_type)
        if expected:
            return isinstance(value, expected)
        
        return True
    
    def _normalize_record(
        self,
        record: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Normalize a memory record with defaults and context.
        
        Args:
            record: Raw memory record
            context: Capture context
            
        Returns:
            Normalized memory record
        """
        default_memory_type = self.config.get("default_memory_type", "observation")
        
        normalized = {
            "title": record.get("title", ""),
            "memory_type": record.get("memory_type", default_memory_type),
            "data": record.get("data", {}),
            "confidence": record.get("confidence", 0.8),
            "importance": record.get("importance", 0.5),
            "summary": record.get("summary", ""),
            "tags": record.get("tags", []),
            "scope_type": record.get("scope_type") or context.get("scope_type", "conversation"),
            "scope_key": record.get("scope_key") or context.get("scope_key", ""),
            "source_type": "conversation",
            "producer_mode": "main_agent",
            "created_from_turn_count": context.get("turn_count", 0)
        }
        
        return normalized
    
    def _format_schema_for_prompt(self, schema: Dict[str, Any]) -> str:
        """
        Format JSON schema as a human-readable prompt addition.
        
        Args:
            schema: JSON schema dict
            
        Returns:
            Formatted schema description
        """
        if not schema:
            return ""
        
        lines = ["\n### Schema Constraints\n"]
        
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        if properties:
            lines.append("The `data` field should follow this structure:\n")
            
            for prop_name, prop_def in properties.items():
                prop_type = prop_def.get("type", "any")
                prop_desc = prop_def.get("description", "")
                is_required = prop_name in required
                
                req_marker = " (required)" if is_required else ""
                desc_str = f" - {prop_desc}" if prop_desc else ""
                
                lines.append(f"- `{prop_name}`: {prop_type}{req_marker}{desc_str}")
        
        return "\n".join(lines)
    
    def _render_template(self, template: str, context: Optional[Dict[str, Any]]) -> str:
        """
        Render a Jinja2 template with context variables.
        
        Args:
            template: Jinja2 template string
            context: Template context variables
            
        Returns:
            Rendered template string
        """
        if not context:
            return template
        
        try:
            from jinja2 import Template
            tmpl = Template(template)
            return tmpl.render(**context)
        except Exception as e:
            frappe.logger().warning(f"Template render error: {e}")
            return template
    
    def _calculate_latency(self, start_time: datetime) -> int:
        """Calculate elapsed time in milliseconds."""
        elapsed = (datetime.now() - start_time).total_seconds()
        return int(elapsed * 1000)
    
    def get_latency_impact(self) -> str:
        """Return latency impact classification."""
        return "zero"
    
    def get_producer(self) -> str:
        """Return the producer type for this capture mode."""
        return "main_agent"


class InPromptCaptureResponseBuilder:
    """
    Helper class to build structured responses with memory updates.
    
    This utility helps agents construct properly formatted responses
    for in-prompt capture mode.
    """
    
    def __init__(self, response_text: str = ""):
        self.response_text = response_text
        self.memory_records = []
    
    def set_response(self, text: str) -> "InPromptCaptureResponseBuilder":
        """Set the main response text."""
        self.response_text = text
        return self
    
    def add_memory(
        self,
        title: str,
        memory_type: str,
        data: Dict[str, Any],
        confidence: float = 0.8,
        importance: float = 0.5,
        summary: str = "",
        tags: Optional[List[str]] = None
    ) -> "InPromptCaptureResponseBuilder":
        """
        Add a memory record to the response.
        
        Args:
            title: Brief descriptive title
            memory_type: Type of memory (profile, fact, plan, etc.)
            data: Structured memory data
            confidence: Confidence score (0.0-1.0)
            importance: Importance score (0.0-1.0)
            summary: Optional human-readable summary
            tags: Optional list of tags
            
        Returns:
            Self for method chaining
        """
        self.memory_records.append({
            "title": title,
            "memory_type": memory_type,
            "data": data,
            "confidence": max(0.0, min(1.0, confidence)),
            "importance": max(0.0, min(1.0, importance)),
            "summary": summary,
            "tags": tags or []
        })
        return self
    
    def build(self) -> Dict[str, Any]:
        """
        Build the structured response dict.
        
        Returns:
            Response dict with memory_update field
        """
        return {
            "response": self.response_text,
            "memory_update": {
                "has_updates": len(self.memory_records) > 0,
                "records": self.memory_records
            }
        }
    
    def to_json(self) -> str:
        """Convert response to JSON string."""
        return json.dumps(self.build(), indent=2)


def create_in_prompt_capture(config: Dict[str, Any]) -> InPromptCaptureMode:
    """
    Factory function to create an InPromptCaptureMode instance.
    
    Args:
        config: Configuration dict
        
    Returns:
        InPromptCaptureMode instance
    """
    return InPromptCaptureMode(config)
