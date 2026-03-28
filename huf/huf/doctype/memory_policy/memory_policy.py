# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MemoryPolicy(Document):
	"""
	Defines how an agent performs memory capture.
	
	A policy controls when, how, and what memories are captured
	for an agent, including the capture mode, frequency, schema,
	and quality thresholds.
	"""
	
	def validate(self):
		"""Validate policy configuration."""
		self._validate_memory_agent()
		self._validate_frequency()
		self._validate_confidence()
		self._validate_retrieval_config()
		self._validate_indexing_config()
	
	def _validate_memory_agent(self):
		"""Ensure memory agent is set when capture owner is memory_agent."""
		if self.capture_owner == "memory_agent" and not self.memory_agent:
			frappe.throw("Memory Agent is required when Capture Owner is set to 'memory_agent'")
		
		# Validate memory agent is different from the linked agent
		if self.memory_agent and self.agent and self.memory_agent == self.agent:
			frappe.throw("Memory Agent cannot be the same as the main Agent")
	
	def _validate_frequency(self):
		"""Validate frequency settings."""
		if self.capture_frequency_type in ["every_n_runs", "every_n_turns"]:
			if not self.capture_frequency_value or self.capture_frequency_value < 1:
				frappe.throw("Capture Frequency Value must be at least 1 for 'every_n' types")
		
		if self.conversation_end_strategy == "idle_timeout":
			if not self.idle_timeout_minutes or self.idle_timeout_minutes < 1:
				frappe.throw("Idle Timeout Minutes must be at least 1")
	
	def _validate_confidence(self):
		"""Validate confidence threshold."""
		if self.min_confidence is not None:
			if self.min_confidence < 0 or self.min_confidence > 1:
				frappe.throw("Minimum Confidence must be between 0.0 and 1.0")
	
	def _validate_retrieval_config(self):
		"""Validate retrieval configuration."""
		if self.max_items_to_inject is not None and self.max_items_to_inject < 1:
			frappe.throw("Max Items to Inject must be at least 1")
		
		if self.max_tokens_to_inject is not None and self.max_tokens_to_inject < 1:
			frappe.throw("Max Tokens to Inject must be at least 1")
	
	def _validate_indexing_config(self):
		"""Validate indexing configuration."""
		if self.enable_vector_index and not self.vector_backend:
			frappe.throw("Vector Backend is required when Vector Index is enabled")
		
		if self.enable_fts_index and not self.fts_backend:
			frappe.throw("FTS Backend is required when FTS Index is enabled")
	
	def should_capture_on_run(self, run_number: int) -> bool:
		"""
		Check if capture should happen on a given run number.
		
		Args:
			run_number: The current run number
			
		Returns:
			True if capture should occur
		"""
		if not self.enabled:
			return False
		
		if self.capture_frequency_type == "every_run":
			return True
		elif self.capture_frequency_type == "every_n_runs":
			return run_number % self.capture_frequency_value == 0
		elif self.capture_frequency_type == "manual":
			return False
		
		# For other types, let the caller handle
		return True
	
	def should_capture_on_turn(self, turn_count: int) -> bool:
		"""
		Check if capture should happen on a given turn count.
		
		Args:
			turn_count: The current turn count
			
		Returns:
			True if capture should occur
		"""
		if not self.enabled:
			return False
		
		if self.capture_frequency_type == "every_n_turns":
			return turn_count % self.capture_frequency_value == 0
		
		return False
	
	def check_confidence_threshold(self, confidence: float) -> bool:
		"""
		Check if a confidence score meets the threshold.
		
		Args:
			confidence: The confidence score to check
			
		Returns:
			True if meets threshold or no threshold set
		"""
		if self.min_confidence is None:
			return True
		return confidence >= self.min_confidence
	
	def get_effective_schema(self) -> dict:
		"""
		Get the effective capture schema.
		
		Returns:
			The schema as a dictionary, or None if open schema
		"""
		if self.allow_open_schema:
			return None
		
		if self.capture_schema_json:
			import json
			try:
				return json.loads(self.capture_schema_json)
			except json.JSONDecodeError:
				frappe.throw("Invalid JSON in Capture Schema")
		
		return None
	
	@staticmethod
	def get_active_policy_for_agent(agent_name: str) -> "MemoryPolicy":
		"""
		Get the active memory policy for an agent.
		
		Args:
			agent_name: The name of the agent
			
		Returns:
			MemoryPolicy document or None
		"""
		policies = frappe.get_all(
			"Memory Policy",
			filters={
				"agent": agent_name,
				"enabled": 1
			},
			order_by="modified desc",
			limit=1
		)
		
		if policies:
			return frappe.get_doc("Memory Policy", policies[0].name)
		
		return None
	
	@staticmethod
	def get_default_policy() -> "MemoryPolicy":
		"""
		Get a default, agent-agnostic memory policy.
		
		Returns:
			MemoryPolicy document or None
		"""
		policies = frappe.get_all(
			"Memory Policy",
			filters={
				"enabled": 1,
				"agent": ["is", "not set"]
			},
			order_by="modified desc",
			limit=1
		)
		
		if policies:
			return frappe.get_doc("Memory Policy", policies[0].name)
		
		return None
