# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Memory Capture Modes Module

Defines the capture mode classes for HUF Memory System.
Capture modes define WHO performs the extraction and WHEN during the request lifecycle.

Capture Modes:
- in_prompt: Memory extracted during main agent inference
- post_sync: Synchronous extraction after main response
- post_async: Asynchronous extraction via background job
- specialized_agent: Dedicated memory agent performs extraction
- rule_only: Deterministic extraction without LLM
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum


class CaptureModeType(str, Enum):
	"""Enumeration of supported capture modes."""
	IN_PROMPT = "in_prompt"
	POST_SYNC = "post_sync"
	POST_ASYNC = "post_async"
	SPECIALIZED_AGENT = "specialized_agent"
	RULE_ONLY = "rule_only"


class CaptureMode:
	"""
	Base class for memory capture modes.
	
	All capture modes must implement:
	- execute(): Perform the capture operation
	- validate(): Validate configuration
	- get_latency_impact(): Return latency characteristics
	"""
	
	def __init__(self, config: Dict[str, Any]):
		self.config = config
		self.mode_type = None
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""Execute the capture operation. Must be implemented by subclasses."""
		raise NotImplementedError
		
	def validate(self) -> bool:
		"""Validate capture mode configuration."""
		return True
		
	def get_latency_impact(self) -> str:
		"""Return latency impact: 'zero', 'minimal', 'high', 'variable'."""
		return "minimal"
		
	def get_producer(self) -> str:
		"""Return the producer type for this capture mode."""
		return "main_agent"


class InPromptCapture(CaptureMode):
	"""
	In-Prompt Capture Mode
	
	Memory instructions are prepended to the main agent system prompt.
	Agent outputs memory updates as part of its JSON response structure.
	Memory fields are extracted from the response and committed synchronously.
	Schema validation occurs post-response before write.
	
	Mode ID: in_prompt
	Execution Phase: During main agent inference
	Latency Impact: Zero (part of main request)
	Producer: Main agent
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.mode_type = CaptureModeType.IN_PROMPT
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute in-prompt capture.
		
		Args:
			context: Contains 'response_data' with memory fields from agent output
			
		Returns:
			Dict with 'records_created', 'records_updated', 'validation_errors'
		"""
		response_data = context.get("response_data", {})
		memory_payload = response_data.get("memory_update", {})
		
		if not memory_payload:
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": [],
				"skipped": True,
				"reason": "No memory payload in response"
			}
		
		# Validate against schema if required
		validation_errors = []
		if self.config.get("require_json_schema_match"):
			schema = self.config.get("schema_json", {})
			if schema:
				validation_errors = self._validate_schema(memory_payload, schema)
		
		if validation_errors:
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": validation_errors,
				"skipped": True,
				"reason": "Schema validation failed"
			}
		
		return {
			"records_created": 1 if memory_payload else 0,
			"records_updated": 0,
			"validation_errors": [],
			"skipped": False,
			"payload": memory_payload
		}
	
	def _validate_schema(self, payload: Dict, schema: Dict) -> List[str]:
		"""Validate payload against JSON schema."""
		errors = []
		required = schema.get("required", [])
		properties = schema.get("properties", {})
		
		for field in required:
			if field not in payload:
				errors.append(f"Missing required field: {field}")
		
		for field, value in payload.items():
			if field in properties:
				prop_def = properties[field]
				expected_type = prop_def.get("type")
				if expected_type and not self._check_type(value, expected_type):
					errors.append(f"Field '{field}' has wrong type. Expected {expected_type}")
		
		return errors
	
	def _check_type(self, value: Any, expected_type: str) -> bool:
		"""Check if value matches expected type."""
		type_map = {
			"string": str,
			"integer": int,
			"number": (int, float),
			"boolean": bool,
			"array": list,
			"object": dict
		}
		expected = type_map.get(expected_type)
		if expected:
			return isinstance(value, expected)
		return True
		
	def get_latency_impact(self) -> str:
		return "zero"
		
	def get_producer(self) -> str:
		return "main_agent"


class PostSyncCapture(CaptureMode):
	"""
	Post-Response Synchronous Capture Mode
	
	Main agent response is returned to controller.
	Capture prompt + conversation context is sent to extraction model.
	Memory record is created/updated synchronously.
	User receives response only after memory commit succeeds.
	
	Mode ID: post_sync
	Execution Phase: After main response, before returning to user
	Latency Impact: High (blocks user response)
	Producer: Main agent or memory agent
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.mode_type = CaptureModeType.POST_SYNC
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute post-response synchronous capture.
		
		Args:
			context: Contains 'conversation', 'run', 'agent_response'
			
		Returns:
			Dict with capture results
		"""
		conversation = context.get("conversation", {})
		run = context.get("run", {})
		agent_response = context.get("agent_response", "")
		
		# Build extraction prompt
		capture_prompt = self._build_capture_prompt(conversation, agent_response)
		
		# Call extraction (synchronous - blocks user response)
		try:
			extraction_result = self._call_extraction_model(capture_prompt, context)
			
			return {
				"records_created": 1 if extraction_result else 0,
				"records_updated": 0,
				"validation_errors": [],
				"skipped": False,
				"payload": extraction_result,
				"latency_ms": extraction_result.get("_latency_ms", 0)
			}
		except Exception as e:
			fallback = self.config.get("fallback_on_error", "skip")
			if fallback == "fail":
				raise
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": [str(e)],
				"skipped": True,
				"reason": f"Extraction failed: {str(e)}"
			}
	
	def _build_capture_prompt(self, conversation: Dict, agent_response: str) -> str:
		"""Build the capture extraction prompt."""
		base_prompt = self.config.get("capture_prompt", """
		Extract structured memory from the conversation context.
		Focus on user preferences, facts, plans, and insights.
		Return valid JSON matching the schema.
		""")
		
		return f"""{base_prompt}

Conversation Context:
{conversation}

Agent Response:
{agent_response}

Extract and return structured memory as JSON."""
	
	def _call_extraction_model(self, prompt: str, context: Dict) -> Dict:
		"""Call the extraction model (placeholder for actual implementation)."""
		# This would integrate with HUF's AI provider system
		# For now, return a placeholder structure
		return {
			"_latency_ms": 0,
			"_model_used": self.config.get("capture_agent", "default"),
			# Actual extraction would be here
		}
		
	def get_latency_impact(self) -> str:
		return "high"
		
	def get_producer(self) -> str:
		return self.config.get("capture_agent") or "main_agent"


class PostAsyncCapture(CaptureMode):
	"""
	Post-Response Asynchronous Capture Mode
	
	User response is returned immediately.
	Capture job is enqueued to background queue (RQ/background job).
	Job runs with conversation context snapshot.
	Memory record creation is eventual consistency.
	Failure is logged but does not block user.
	
	Mode ID: post_async
	Execution Phase: Background job after user response sent
	Latency Impact: Zero (non-blocking)
	Producer: Main agent, memory agent, or post-run processor
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.mode_type = CaptureModeType.POST_ASYNC
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute post-response asynchronous capture.
		Enqueues a background job for memory extraction.
		
		Args:
			context: Contains conversation and run data
			
		Returns:
			Dict with job enqueue status
		"""
		conversation_id = context.get("conversation_id")
		run_id = context.get("run_id")
		
		# Prepare context snapshot for background processing
		snapshot = self._prepare_context_snapshot(context)
		
		# Enqueue background job
		try:
			job_name = f"memory_capture_{conversation_id}_{datetime.now().timestamp()}"
			
			# Use Frappe's background job system
			frappe.enqueue(
				method="huf.memory.capture.process_async_capture",
				queue=self.config.get("queue_name", "memory_capture"),
				job_name=job_name,
				conversation_id=conversation_id,
				run_id=run_id,
				snapshot=snapshot,
				config=self.config,
				timeout=300,
				retry_count=self.config.get("retry_count", 3)
			)
			
			return {
				"records_created": 0,  # Created asynchronously
				"records_updated": 0,
				"validation_errors": [],
				"skipped": False,
				"job_enqueued": True,
				"job_name": job_name,
				"async": True
			}
		except Exception as e:
			frappe.log_error(f"Failed to enqueue memory capture: {str(e)}", "Memory Capture")
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": [str(e)],
				"skipped": True,
				"reason": f"Enqueue failed: {str(e)}"
			}
	
	def _prepare_context_snapshot(self, context: Dict) -> Dict:
		"""Prepare a snapshot of context for background processing."""
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
			"captured_at": datetime.now().isoformat()
		}
		
	def get_latency_impact(self) -> str:
		return "zero"
		
	def get_producer(self) -> str:
		return self.config.get("capture_agent") or "post_run_processor"


class SpecializedAgentCapture(CaptureMode):
	"""
	Specialized Memory Agent Capture Mode
	
	Memory agent is a separate Agent record with specialized prompt.
	May use cheaper/faster model optimized for extraction.
	Receives conversation context + extraction instructions.
	Returns structured memory payload.
	Can run sync or async depending on trigger.
	
	Mode ID: specialized_agent
	Execution Phase: Configurable (sync or async)
	Latency Impact: Varies by execution phase
	Producer: Dedicated memory agent instance
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.mode_type = CaptureModeType.SPECIALIZED_AGENT
		self.memory_agent_id = config.get("memory_agent")
		
	def validate(self) -> bool:
		"""Validate that memory agent is specified."""
		if not self.memory_agent_id:
			frappe.throw(_("Specialized agent capture requires a memory_agent to be specified"))
		return True
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute specialized memory agent capture.
		
		Args:
			context: Conversation and extraction context
			
		Returns:
			Dict with extraction results
		"""
		# Validate memory agent exists
		if not frappe.db.exists("Agent", self.memory_agent_id):
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": [f"Memory agent '{self.memory_agent_id}' not found"],
				"skipped": True,
				"reason": "Memory agent not found"
			}
		
		# Prepare context for memory agent
		execution_timing = self.config.get("execution_timing", "post_response_async")
		
		if execution_timing == "post_response_async":
			# Delegate to async capture
			async_capture = PostAsyncCapture(self.config)
			return async_capture.execute(context)
		else:
			# Synchronous execution with specialized agent
			return self._run_specialized_agent(context)
	
	def _run_specialized_agent(self, context: Dict) -> Dict:
		"""Run the specialized memory agent synchronously."""
		from huf.ai.agent_integration import run_agent_sync
		
		# Prepare prompt for memory agent
		prompt = self._prepare_agent_prompt(context)
		
		try:
			result = run_agent_sync(
				agent_name=self.memory_agent_id,
				prompt=prompt,
				channel_id=f"memory_capture_{context.get('conversation_id', 'unknown')}"
			)
			
			response = result.get("response", "{}")
			# Parse JSON response
			try:
				import json
				payload = json.loads(response)
			except json.JSONDecodeError:
				payload = {"raw_response": response}
			
			return {
				"records_created": 1 if payload else 0,
				"records_updated": 0,
				"validation_errors": [],
				"skipped": False,
				"payload": payload,
				"agent_run_id": result.get("agent_run_id")
			}
		except Exception as e:
			return {
				"records_created": 0,
				"records_updated": 0,
				"validation_errors": [str(e)],
				"skipped": True,
				"reason": f"Specialized agent failed: {str(e)}"
			}
	
	def _prepare_agent_prompt(self, context: Dict) -> str:
		"""Prepare the prompt for the specialized memory agent."""
		pass_full_history = self.config.get("pass_full_history", True)
		pass_summary_only = self.config.get("pass_summary_only", False)
		
		if pass_summary_only:
			conversation_text = context.get("conversation_summary", "")
		else:
			conversation = context.get("conversation", {})
			messages = conversation.get("messages", [])
			
			if not pass_full_history:
				# Limit to recent messages
				messages = messages[-10:]
			
			conversation_text = "\n".join([
				f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
				for msg in messages
			])
		
		return f"""Extract structured memory from the following conversation.

Conversation:
{conversation_text}

Extract relevant facts, preferences, plans, and insights as structured JSON.
Focus on information that would be useful for future interactions."""
		
	def get_latency_impact(self) -> str:
		execution_timing = self.config.get("execution_timing", "post_response_async")
		if execution_timing == "post_response_async":
			return "zero"
		return "variable"
		
	def get_producer(self) -> str:
		return self.memory_agent_id or "memory_agent"


class RuleOnlyCapture(CaptureMode):
	"""
	Rule-Only Capture Mode
	
	No LLM inference for extraction.
	Memory fields populated from:
	- Exact context values (user_id, timestamp, state flags)
	- Regex/template extractions
	- Tool call outputs
	- System event payloads
	JSON Path or Jinja2 template mapping.
	Direct commit to memory record.
	
	Mode ID: rule_only
	Execution Phase: Deterministic (sync)
	Latency Impact: Minimal (no LLM call)
	Producer: Rule engine
	"""
	
	RULE_TYPES = ["static", "context", "regex", "tool", "computed"]
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.mode_type = CaptureModeType.RULE_ONLY
		self.rules = config.get("rules", [])
		
	def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute rule-only capture.
		
		Args:
			context: Contains conversation, run, tool outputs, etc.
			
		Returns:
			Dict with extracted fields
		"""
		import re
		from frappe.utils import now_datetime
		
		extracted = {}
		errors = []
		
		for rule in self.rules:
			try:
				field_name = rule.get("field")
				rule_type = rule.get("source")
				
				if rule_type == "static":
					# Fixed value assignment
					value = rule.get("value", "")
					# Support basic template variables
					if "{{" in value:
						value = value.replace("{{ now() }}", now_datetime())
					extracted[field_name] = value
					
				elif rule_type == "context":
					# Extract from conversation/run context
					path = rule.get("path", "")
					value = self._get_nested_value(context, path)
					if value is not None:
						extracted[field_name] = value
						
				elif rule_type == "regex":
					# Pattern match on messages
					pattern = rule.get("pattern", "")
					on_match = rule.get("on_match")
					source_text = rule.get("source_text", "user_messages")
					
					text = self._get_text_for_regex(context, source_text)
					match = re.search(pattern, text, re.IGNORECASE)
					
					if match:
						if on_match:
							extracted[field_name] = on_match
						elif match.groups():
							extracted[field_name] = match.group(1)
						else:
							extracted[field_name] = match.group(0)
								
				elif rule_type == "tool":
					# Capture from tool outputs
					tool_name = rule.get("tool_name")
					tool_outputs = context.get("tool_outputs", [])
					
					for output in tool_outputs:
						if output.get("tool") == tool_name:
							path = rule.get("path", "")
							value = self._get_nested_value(output, path)
							if value is not None:
								extracted[field_name] = value
								break
									
				elif rule_type == "computed":
					# Derived from other fields
					formula = rule.get("formula", "")
					# Simple computed field support
					if formula == "turn_count":
						messages = context.get("conversation", {}).get("messages", [])
						extracted[field_name] = len(messages)
					elif formula == "duration_seconds":
						# Calculate from timestamps if available
						extracted[field_name] = 0  # Placeholder
														
			except Exception as e:
				errors.append(f"Rule '{rule.get('field', 'unknown')}' failed: {str(e)}")
		
		return {
			"records_created": 1 if extracted else 0,
			"records_updated": 0,
			"validation_errors": errors,
			"skipped": False if extracted else True,
			"payload": extracted
		}
	
	def _get_nested_value(self, data: Dict, path: str) -> Any:
		"""Get a nested value using dot notation."""
		parts = path.split(".")
		current = data
		
		for part in parts:
			if isinstance(current, dict) and part in current:
				current = current[part]
			else:
				return None
						
		return current
	
	def _get_text_for_regex(self, context: Dict, source: str) -> str:
		"""Get text to apply regex against."""
		conversation = context.get("conversation", {})
		messages = conversation.get("messages", [])
		
		if source == "user_messages":
			return "\n".join([
				msg.get("content", "")
				for msg in messages
				if msg.get("role") == "user"
			])
		elif source == "all_messages":
			return "\n".join([
				f"{msg.get('role')}: {msg.get('content', '')}"
				for msg in messages
			])
		elif source == "agent_response":
			return context.get("agent_response", "")
					
		return ""
		
	def get_latency_impact(self) -> str:
		return "minimal"
		
	def get_producer(self) -> str:
		return "rule_engine"


# Factory function to get capture mode instance
def get_capture_mode(config: Dict[str, Any]) -> CaptureMode:
	"""
	Factory function to create appropriate capture mode instance.
	
	Args:
		config: Configuration dict with 'capture_mode' key
		
	Returns:
		CaptureMode instance
		
	Raises:
		ValueError: If capture_mode is not recognized
	"""
	mode_id = config.get("capture_mode", "post_async")
	
	mode_map = {
		"in_prompt": InPromptCapture,
		"post_sync": PostSyncCapture,
		"post_async": PostAsyncCapture,
		"specialized_agent": SpecializedAgentCapture,
		"rule_only": RuleOnlyCapture
	}
	
	mode_class = mode_map.get(mode_id)
	if not mode_class:
		raise ValueError(f"Unknown capture mode: {mode_id}")
	
	return mode_class(config)


# Background job handler for async capture
def process_async_capture(
	conversation_id: str,
	run_id: str,
	snapshot: Dict,
	config: Dict[str, Any]
):
	"""
	Background job handler for asynchronous memory capture.
	
	This function is called by Frappe's background job system.
	"""
	try:
		# Create a sync capture instance for processing
		sync_capture = PostSyncCapture(config)
		
		# Reconstruct context from snapshot
		context = {
			"conversation_id": conversation_id,
			"run_id": run_id,
			"conversation": {"messages": snapshot.get("messages", [])},
			"agent_response": snapshot.get("agent_response"),
			**snapshot
		}
		
		# Execute capture
		result = sync_capture.execute(context)
		
		# Here you would create/update the actual Memory Record
		# This is handled by the processor module
		
		frappe.logger().info(f"Async memory capture completed for conversation {conversation_id}")
		
		return result
		
	except Exception as e:
		frappe.log_error(
			f"Async memory capture failed for conversation {conversation_id}: {str(e)}",
			"Memory Capture"
		)
		raise