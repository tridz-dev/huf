# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Memory Capture Triggers Module

Defines the trigger system for HUF Memory System.
Triggers define WHEN memory capture is executed.

Trigger Types:
- every_run: Every agent run/turn
- every_n_runs: Every N runs (configurable)
- every_n_turns: Every N turns in conversation
- after_tool_call: After specific tool execution
- final_response_only: Only on final assistant response
- conversation_end: When conversation is marked complete
- idle_timeout: After inactivity threshold
- manual: Explicit user/admin trigger
- scheduled: Cron-based consolidation
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class TriggerType(str, Enum):
	"""Enumeration of supported trigger types."""
	EVERY_RUN = "every_run"
	EVERY_N_RUNS = "every_n_runs"
	EVERY_N_TURNS = "every_n_turns"
	AFTER_TOOL_CALL = "after_tool_call"
	FINAL_RESPONSE_ONLY = "final_response_only"
	CONVERSATION_END = "conversation_end"
	IDLE_TIMEOUT = "idle_timeout"
	MANUAL = "manual"
	SCHEDULED = "scheduled"


class TriggerResult:
	"""Result of a trigger evaluation."""
	
	def __init__(
		self,
		should_capture: bool,
		trigger_type: str,
		reason: str = "",
		metadata: Optional[Dict] = None
	):
		self.should_capture = should_capture
		self.trigger_type = trigger_type
		self.reason = reason
		self.metadata = metadata or {}
		self.timestamp = datetime.now().isoformat()
		
	def to_dict(self) -> Dict[str, Any]:
		return {
			"should_capture": self.should_capture,
			"trigger_type": self.trigger_type,
			"reason": self.reason,
			"metadata": self.metadata,
			"timestamp": self.timestamp
		}


class MemoryTrigger:
	"""
	Base class for memory capture triggers.
	
	All triggers must implement:
	- evaluate(): Check if trigger conditions are met
	- get_trigger_type(): Return trigger type identifier
	"""
	
	def __init__(self, config: Dict[str, Any]):
		self.config = config
		self.trigger_type = None
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""Evaluate if trigger conditions are met. Must be implemented by subclasses."""
		raise NotImplementedError
		
	def get_trigger_type(self) -> str:
		"""Return the trigger type identifier."""
		return self.trigger_type
		
	def _get_conversation(self, context: Dict) -> Dict:
		"""Helper to safely get conversation from context."""
		return context.get("conversation", {}) or {}
		
	def _get_run(self, context: Dict) -> Dict:
		"""Helper to safely get run from context."""
		return context.get("run", {}) or {}


class EveryRunTrigger(MemoryTrigger):
	"""
	Every Run Trigger
	
	Fire after every non-error agent response.
	Configurable debounce (min_seconds_between).
	Deduplication via hash of context snapshot.
	
	Trigger ID: every_run
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.EVERY_RUN
		self.min_seconds = config.get("min_seconds_between", 0)
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if capture should trigger on this run.
		
		Args:
			context: Contains 'conversation', 'run', 'last_capture_at'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		conversation = self._get_conversation(context)
		last_capture_at = context.get("last_capture_at")
		
		# Check debounce
		if last_capture_at and self.min_seconds > 0:
			last_time = datetime.fromisoformat(last_capture_at)
			elapsed = (datetime.now() - last_time).total_seconds()
			
			if elapsed < self.min_seconds:
				return TriggerResult(
					should_capture=False,
					trigger_type=self.trigger_type,
					reason=f"Debounced: {elapsed:.1f}s since last capture",
					metadata={"elapsed_seconds": elapsed}
				)
		
		# Check for errors in run
		run = self._get_run(context)
		if run.get("status") == "error":
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="Run ended in error state"
			)
		
		return TriggerResult(
			should_capture=True,
			trigger_type=self.trigger_type,
			reason="Every run trigger fired",
			metadata={
				"conversation_id": context.get("conversation_id"),
				"run_id": context.get("run_id")
			}
		)


class EveryNRunsTrigger(MemoryTrigger):
	"""
	Every N Runs Trigger
	
	Counter maintained on Agent Run record.
	Fire when run_count % N == 0.
	Counter resets per conversation or global (configurable).
	
	Trigger ID: every_n_runs
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.EVERY_N_RUNS
		self.frequency = config.get("frequency_value", 5)
		self.counter_scope = config.get("counter_scope", "conversation")
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if capture should trigger based on run counter.
		
		Args:
			context: Contains 'run_count', 'conversation_id'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		run_count = context.get("run_count", 0)
		
		if run_count == 0:
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="First run, not triggering"
			)
		
		if run_count % self.frequency == 0:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Run count {run_count} is multiple of {self.frequency}",
				metadata={
					"run_count": run_count,
					"frequency": self.frequency,
					"counter_scope": self.counter_scope
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason=f"Run count {run_count} not multiple of {self.frequency}",
			metadata={
				"run_count": run_count,
				"next_trigger_at": (run_count // self.frequency + 1) * self.frequency
			}
		)


class EveryNTurnsTrigger(MemoryTrigger):
	"""
	Every N Turns Trigger
	
	Counter maintained on Agent Conversation record.
	Fire when turn_count % N == 0.
	Turn counting includes user + assistant exchanges.
	
	Trigger ID: every_n_turns
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.EVERY_N_TURNS
		self.frequency = config.get("frequency_value", 10)
		self.count_both_roles = config.get("count_both_roles", True)
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if capture should trigger based on turn counter.
		
		Args:
			context: Contains 'conversation' with 'messages' or 'turn_count'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		conversation = self._get_conversation(context)
		
		# Get turn count - either provided directly or calculated from messages
		turn_count = context.get("turn_count")
		if turn_count is None:
			messages = conversation.get("messages", [])
			if self.count_both_roles:
				# Count user + assistant exchanges
				user_msgs = sum(1 for m in messages if m.get("role") == "user")
				assistant_msgs = sum(1 for m in messages if m.get("role") == "assistant")
				turn_count = min(user_msgs, assistant_msgs)
			else:
				# Count only user messages
				turn_count = sum(1 for m in messages if m.get("role") == "user")
		
		if turn_count == 0:
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="No turns yet"
			)
		
		if turn_count % self.frequency == 0:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Turn count {turn_count} is multiple of {self.frequency}",
				metadata={
					"turn_count": turn_count,
					"frequency": self.frequency,
					"count_both_roles": self.count_both_roles
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason=f"Turn count {turn_count} not multiple of {self.frequency}",
			metadata={
				"turn_count": turn_count,
				"next_trigger_at": (turn_count // self.frequency + 1) * self.frequency
			}
		)


class AfterToolCallTrigger(MemoryTrigger):
	"""
	After Tool Call Trigger
	
	Registered tool names trigger capture.
	Tool input/output included in context.
	Fire after tool completes, before final response.
	
	Trigger ID: after_tool_call
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.AFTER_TOOL_CALL
		self.watched_tools = config.get("watched_tools", [])
		self.capture_tool_output = config.get("capture_tool_output", True)
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if capture should trigger based on tool calls.
		
		Args:
			context: Contains 'tool_calls', 'tool_outputs'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		tool_calls = context.get("tool_calls", [])
		tool_outputs = context.get("tool_outputs", [])
		
		if not tool_calls:
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="No tool calls in context"
			)
		
		# Check if any watched tool was called
		triggered_tools = []
		for tool_call in tool_calls:
			tool_name = tool_call.get("tool") or tool_call.get("name")
			if tool_name in self.watched_tools:
				triggered_tools.append(tool_name)
		
		if triggered_tools:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Watched tools called: {', '.join(triggered_tools)}",
				metadata={
					"triggered_tools": triggered_tools,
					"tool_outputs_included": self.capture_tool_output,
					"total_tool_calls": len(tool_calls)
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason=f"No watched tools called. Watched: {self.watched_tools}",
			metadata={
				"tools_called": [t.get("tool") or t.get("name") for t in tool_calls],
				"watched_tools": self.watched_tools
			}
		)


class FinalResponseOnlyTrigger(MemoryTrigger):
	"""
	Final Response Only Trigger
	
	Fire only on assistant message (not tool calls).
	Skip intermediate tool-turns in multi-step runs.
	
	Trigger ID: final_response_only
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.FINAL_RESPONSE_ONLY
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if this is a final response (not intermediate tool call).
		
		Args:
			context: Contains 'run', 'is_final_response'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		# Explicit flag if provided
		is_final = context.get("is_final_response")
		if is_final is not None:
			if is_final:
				return TriggerResult(
					should_capture=True,
					trigger_type=self.trigger_type,
					reason="Explicit final response flag"
				)
			else:
				return TriggerResult(
					should_capture=False,
					trigger_type=self.trigger_type,
					reason="Not final response (explicit flag)"
				)
		
		# Infer from run status
		run = self._get_run(context)
		run_status = run.get("status")
		
		# If run is completed, this is final
		if run_status == "completed":
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason="Run completed - final response"
			)
		
		# Check if there are pending tool calls
		has_pending_tools = context.get("has_pending_tool_calls", False)
		if has_pending_tools:
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="Pending tool calls - not final response"
			)
		
		# Default to capturing if no pending tools
		return TriggerResult(
			should_capture=True,
			trigger_type=self.trigger_type,
			reason="No pending tool calls - treating as final"
		)


class ConversationEndTrigger(MemoryTrigger):
	"""
	Conversation End Trigger
	
	Triggered by conversation state change to 'ended'.
	Can be synchronous or queued for processing.
	Always captures full conversation context.
	
	End Detection Strategies:
	- manual_close: User/admin explicitly closes conversation
	- idle_timeout: No activity for idle_timeout_minutes
	- heuristic: Agent classifies conversation as complete
	- workflow_complete: Workflow reaches terminal state
	
	Trigger ID: conversation_end
	"""
	
	END_STRATEGIES = ["manual_close", "idle_timeout", "heuristic", "workflow_complete"]
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.CONVERSATION_END
		self.end_strategy = config.get("end_strategy", "manual_close")
		self.capture_full_summary = config.get("capture_full_summary", True)
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if conversation has ended.
		
		Args:
			context: Contains 'conversation', 'end_event'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		conversation = self._get_conversation(context)
		end_event = context.get("end_event")
		
		# Explicit end event
		if end_event:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Explicit end event: {end_event.get('reason', 'unknown')}",
				metadata={
					"end_strategy": end_event.get("strategy", self.end_strategy),
					"capture_full_summary": self.capture_full_summary,
					"ended_at": end_event.get("timestamp")
				}
			)
		
		# Check conversation state
		conversation_state = conversation.get("state") or conversation.get("status")
		if conversation_state == "ended":
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason="Conversation state is 'ended'",
				metadata={
					"end_strategy": self.end_strategy,
					"capture_full_summary": self.capture_full_summary
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason="Conversation not ended"
		)


class IdleTimeoutTrigger(MemoryTrigger):
	"""
	Idle Timeout Trigger
	
	Background job checks for idle conversations.
	Fire on timeout (conversation not explicitly closed).
	May auto-close conversation or just capture state.
	
	Trigger ID: idle_timeout
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.IDLE_TIMEOUT
		self.idle_timeout_minutes = config.get("idle_timeout_minutes", 30)
		self.auto_close_on_timeout = config.get("auto_close_on_timeout", True)
		self.capture_before_close = config.get("capture_before_close", True)
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate if conversation has been idle beyond timeout.
		
		Args:
			context: Contains 'conversation', 'current_time'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		conversation = self._get_conversation(context)
		
		last_activity_at = conversation.get("last_activity_at") or conversation.get("modified")
		if not last_activity_at:
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="No last activity timestamp"
			)
		
		# Parse last activity time
		try:
			if isinstance(last_activity_at, str):
				last_time = datetime.fromisoformat(last_activity_at.replace("Z", "+00:00"))
			else:
				last_time = last_activity_at
		except (ValueError, TypeError):
			return TriggerResult(
				should_capture=False,
				trigger_type=self.trigger_type,
				reason="Invalid last activity timestamp"
			)
		
		# Get current time
		current_time = context.get("current_time")
		if current_time:
			if isinstance(current_time, str):
				now = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
			else:
				now = current_time
		else:
			now = datetime.now()
		
		idle_duration = (now - last_time).total_seconds() / 60  # minutes
		
		if idle_duration >= self.idle_timeout_minutes:
			return TriggerResult(
				should_capture=self.capture_before_close,
				trigger_type=self.trigger_type,
				reason=f"Idle for {idle_duration:.1f} minutes (timeout: {self.idle_timeout_minutes})",
				metadata={
					"idle_minutes": idle_duration,
					"timeout_minutes": self.idle_timeout_minutes,
					"auto_close": self.auto_close_on_timeout,
					"capture_before_close": self.capture_before_close
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason=f"Not idle enough ({idle_duration:.1f} < {self.idle_timeout_minutes} min)",
			metadata={
				"idle_minutes": idle_duration,
				"timeout_minutes": self.idle_timeout_minutes
			}
		)


class ManualTrigger(MemoryTrigger):
	"""
	Manual Trigger
	
	Explicit API endpoint /api/memory/capture
	UI button "Capture Memory Now"
	Admin/operator initiated
	
	Trigger ID: manual
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.MANUAL
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate manual trigger.
		
		Args:
			context: Contains 'manual_trigger', 'triggered_by'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		manual_trigger = context.get("manual_trigger", False)
		triggered_by = context.get("triggered_by", "unknown")
		
		if manual_trigger:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Manually triggered by {triggered_by}",
				metadata={
					"triggered_by": triggered_by,
					"conversation_id": context.get("conversation_id")
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason="No manual trigger flag set"
		)


class ScheduledTrigger(MemoryTrigger):
	"""
	Scheduled Consolidation Trigger
	
	Cron-based trigger via HUF scheduler.
	Processes batches of memory records.
	Typically used for Phase 2+ operations (merge, dedupe).
	
	Trigger ID: scheduled
	"""
	
	def __init__(self, config: Dict[str, Any]):
		super().__init__(config)
		self.trigger_type = TriggerType.SCHEDULED
		self.cron_expression = config.get("cron_expression", "0 2 * * *")
		self.operation = config.get("operation", "consolidate")
		self.scope_filter = config.get("scope_filter", {})
		
	def evaluate(self, context: Dict[str, Any]) -> TriggerResult:
		"""
		Evaluate scheduled trigger.
		
		Args:
			context: Contains 'scheduled_run', 'batch_info'
			
		Returns:
			TriggerResult indicating whether to capture
		"""
		scheduled_run = context.get("scheduled_run", False)
		
		if scheduled_run:
			return TriggerResult(
				should_capture=True,
				trigger_type=self.trigger_type,
				reason=f"Scheduled {self.operation} operation",
				metadata={
					"cron_expression": self.cron_expression,
					"operation": self.operation,
					"scope_filter": self.scope_filter,
					"batch_info": context.get("batch_info", {})
				}
			)
		
		return TriggerResult(
			should_capture=False,
			trigger_type=self.trigger_type,
			reason="Not a scheduled run"
		)


# Factory function to get trigger instance
def get_trigger(config: Dict[str, Any]) -> MemoryTrigger:
	"""
	Factory function to create appropriate trigger instance.
	
	Args:
		config: Configuration dict with 'trigger_type' key
		
	Returns:
		MemoryTrigger instance
		
	Raises:
		ValueError: If trigger_type is not recognized
	"""
	trigger_type = config.get("trigger_type", "every_run")
	
	trigger_map = {
		"every_run": EveryRunTrigger,
		"every_n_runs": EveryNRunsTrigger,
		"every_n_turns": EveryNTurnsTrigger,
		"after_tool_call": AfterToolCallTrigger,
		"final_response_only": FinalResponseOnlyTrigger,
		"conversation_end": ConversationEndTrigger,
		"idle_timeout": IdleTimeoutTrigger,
		"manual": ManualTrigger,
		"scheduled": ScheduledTrigger
	}
	
	trigger_class = trigger_map.get(trigger_type)
	if not trigger_class:
		raise ValueError(f"Unknown trigger type: {trigger_type}")
	
	return trigger_class(config)


# Helper class to manage multiple triggers
class TriggerManager:
	"""
	Manages multiple triggers for memory capture.
	
	Evaluates all registered triggers and returns combined result.
	"""
	
	def __init__(self):
		self.triggers: List[MemoryTrigger] = []
		
	def add_trigger(self, trigger: MemoryTrigger):
		"""Add a trigger to the manager."""
		self.triggers.append(trigger)
		
	def remove_trigger(self, trigger_type: str):
		"""Remove a trigger by type."""
		self.triggers = [t for t in self.triggers if t.get_trigger_type() != trigger_type]
		
	def evaluate_all(self, context: Dict[str, Any]) -> List[TriggerResult]:
		"""
		Evaluate all registered triggers.
		
		Args:
			context: Evaluation context
			
		Returns:
			List of TriggerResult objects
		"""
		results = []
		for trigger in self.triggers:
			try:
				result = trigger.evaluate(context)
				results.append(result)
			except Exception as e:
				frappe.log_error(f"Trigger evaluation failed: {str(e)}", "Memory Trigger")
				results.append(TriggerResult(
					should_capture=False,
					trigger_type=trigger.get_trigger_type(),
					reason=f"Evaluation error: {str(e)}"
				))
		return results
		
	def should_capture(self, context: Dict[str, Any]) -> Optional[TriggerResult]:
		"""
		Check if any trigger says we should capture.
		
		Returns the first positive result, or None if no triggers fire.
		"""
		results = self.evaluate_all(context)
		for result in results:
			if result.should_capture:
				return result
		return None


# Trigger selection matrix helper
TRIGGER_SELECTION_MATRIX = {
	"always_capture": "every_run",
	"cost_conscious_periodic": ["every_n_runs", "every_n_turns"],
	"action_driven": "after_tool_call",
	"summary_only": "final_response_only",
	"complete_conversation": "conversation_end",
	"handle_abandonment": "idle_timeout",
	"on_demand": "manual",
	"batch_processing": "scheduled"
}


def get_recommended_trigger(use_case: str) -> Optional[str]:
	"""
	Get recommended trigger type for a use case.
	
	Args:
		use_case: Key from TRIGGER_SELECTION_MATRIX
		
	Returns:
		Trigger type string or None
	"""
	return TRIGGER_SELECTION_MATRIX.get(use_case)