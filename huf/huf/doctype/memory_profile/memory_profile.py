# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json

class MemoryProfile(Document):
	"""
	Opinionated presets for common memory domains.
	
	Profiles provide default schemas, prompts, and configuration
	for specific use cases like programming, travel planning, CRM, etc.
	"""
	
	def validate(self):
		"""Validate profile configuration."""
		self._validate_schema_json()
		self._validate_type_mapping()
	
	def _validate_schema_json(self):
		"""Validate the schema JSON is well-formed."""
		if self.default_schema_json:
			try:
				json.loads(self.default_schema_json)
			except json.JSONDecodeError as e:
				frappe.throw(f"Invalid JSON in Default Schema: {str(e)}")
	
	def _validate_type_mapping(self):
		"""Validate the type mapping JSON."""
		if self.default_memory_type_mapping:
			try:
				mapping = json.loads(self.default_memory_type_mapping)
				if not isinstance(mapping, dict):
					frappe.throw("Memory Type Mapping must be a JSON object")
			except json.JSONDecodeError as e:
				frappe.throw(f"Invalid JSON in Memory Type Mapping: {str(e)}")
	
	def get_schema(self) -> dict:
		"""
		Get the schema as a Python dictionary.
		
		Returns:
			Schema dictionary
		"""
		if self.default_schema_json:
			return json.loads(self.default_schema_json)
		return {}
	
	def get_type_mapping(self) -> dict:
		"""
		Get the type mapping as a Python dictionary.
		
		Returns:
			Type mapping dictionary
		"""
		if self.default_memory_type_mapping:
			return json.loads(self.default_memory_type_mapping)
		return {}
	
	def get_capture_prompt(self, context: dict = None) -> str:
		"""
		Get the capture prompt, optionally with context substitution.
		
		Args:
			context: Optional dictionary for template substitution
			
		Returns:
			The capture prompt string
		"""
		prompt = self.default_capture_prompt or ""
		
		if context:
			# Simple template substitution
			for key, value in context.items():
				prompt = prompt.replace(f"{{{key}}}", str(value))
		
		return prompt
	
	def infer_memory_type(self, content: str, source_type: str = None) -> str:
		"""
		Infer the memory type based on content and mapping rules.
		
		Args:
			content: The content to analyze
			source_type: Optional source type hint
			
		Returns:
			The inferred memory type
		"""
		mapping = self.get_type_mapping()
		
		if not mapping:
			return "custom"
		
		# Check pattern-based rules
		for pattern, mem_type in mapping.items():
			if pattern.lower() in content.lower():
				return mem_type
		
		return "custom"
	
	@staticmethod
	def get_system_profiles() -> list:
		"""
		Get all system-defined profiles.
		
		Returns:
			List of MemoryProfile documents
		"""
		profile_names = frappe.get_all(
			"Memory Profile",
			filters={"is_system_profile": 1},
			fields=["name"]
		)
		
		return [frappe.get_doc("Memory Profile", p.name) for p in profile_names]
	
	@staticmethod
	def get_profile_by_category(category: str) -> "MemoryProfile":
		"""
		Get the default profile for a category.
		
		Args:
			category: The profile category
			
		Returns:
			MemoryProfile document or None
		"""
		profiles = frappe.get_all(
			"Memory Profile",
			filters={
				"category": category,
				"is_system_profile": 1
			},
			order_by="modified desc",
			limit=1
		)
		
		if profiles:
			return frappe.get_doc("Memory Profile", profiles[0].name)
		
		return None
	
	@staticmethod
	def create_default_profiles():
		"""
		Create the default system profiles if they don't exist.
		This is called during setup or migration.
		"""
		default_profiles = [
			{
				"profile_name": "Programming Memory",
				"description": "For capturing code patterns, conventions, debugging context, and programming-related knowledge",
				"category": "programming",
				"is_system_profile": 1,
				"default_schema_json": json.dumps({
					"memory_type": "code_pattern|convention|debugging|architecture|api_usage",
					"title": "string",
					"content": "string",
					"language": "string",
					"framework": "string",
					"tags": ["string"],
					"confidence": "number"
				}, indent=2),
				"default_capture_prompt": """Analyze the conversation and extract programming-related memories.

Look for:
- Code patterns or idioms discussed
- Conventions or style preferences mentioned
- Debugging solutions or workarounds
- Architecture decisions or design patterns
- API usage patterns or integration details

Return a JSON object with the schema.""",
				"default_capture_stage": "post_response_async",
				"default_frequency": "every_n_turns",
				"default_scope_type": "agent",
				"default_indexing_mode": "fts",
				"default_retrieval_mode": "inject",
				"recommended_model": "gpt-4",
				"recommended_provider": "openai"
			},
			{
				"profile_name": "General Knowledge Memory",
				"description": "For capturing facts, preferences, and reusable general information",
				"category": "general",
				"is_system_profile": 1,
				"default_schema_json": json.dumps({
					"memory_type": "fact|preference|habit|reference",
					"title": "string",
					"content": "string",
					"category": "string",
					"importance": "number",
					"confidence": "number"
				}, indent=2),
				"default_capture_prompt": """Extract factual information and preferences from the conversation.

Focus on:
- Facts about the user (preferences, habits, context)
- General knowledge shared
- Important references or resources
- Recurring themes or interests

Return a JSON object with the schema.""",
				"default_capture_stage": "conversation_end",
				"default_frequency": "conversation_end",
				"default_scope_type": "user",
				"default_indexing_mode": "both",
				"default_retrieval_mode": "hybrid",
				"recommended_model": "gpt-4",
				"recommended_provider": "openai"
			},
			{
				"profile_name": "Travel Planning Memory",
				"description": "For capturing destinations, dates, preferences, and travel constraints",
				"category": "travel",
				"is_system_profile": 1,
				"default_schema_json": json.dumps({
					"memory_type": "destination|date|preference|constraint|booking",
					"title": "string",
					"content": "string",
					"location": "string",
					"dates": {
						"start": "string",
						"end": "string"
					},
					"budget": "string",
					"travelers": "number",
					"confidence": "number"
				}, indent=2),
				"default_capture_prompt": """Extract travel-related information from the conversation.

Capture:
- Destinations mentioned
- Travel dates or date ranges
- Preferences (activities, accommodation, food)
- Constraints (budget, accessibility, etc.)
- Bookings or reservations discussed

Return a JSON object with the schema.""",
				"default_capture_stage": "in_prompt",
				"default_frequency": "every_run",
				"default_scope_type": "conversation",
				"default_indexing_mode": "fts",
				"default_retrieval_mode": "inject",
				"recommended_model": "gpt-4",
				"recommended_provider": "openai"
			},
			{
				"profile_name": "CRM Memory",
				"description": "For capturing customer context, history, and preferences",
				"category": "crm",
				"is_system_profile": 1,
				"default_schema_json": json.dumps({
					"memory_type": "customer_info|interaction|preference|issue|opportunity",
					"title": "string",
					"content": "string",
					"customer_id": "string",
					"sentiment": "positive|neutral|negative",
					"priority": "low|medium|high",
					"follow_up_required": "boolean",
					"confidence": "number"
				}, indent=2),
				"default_capture_prompt": """Extract customer relationship information from the conversation.

Focus on:
- Customer details and identifiers
- Interaction history and context
- Preferences and requirements
- Issues or concerns raised
- Opportunities or upsell potential

Return a JSON object with the schema.""",
				"default_capture_stage": "post_response_async",
				"default_frequency": "every_run",
				"default_scope_type": "namespace",
				"default_indexing_mode": "both",
				"default_retrieval_mode": "hybrid",
				"recommended_model": "gpt-4",
				"recommended_provider": "openai"
			},
			{
				"profile_name": "Documentation Memory",
				"description": "For capturing requirements, decisions, and API contracts",
				"category": "documentation",
				"is_system_profile": 1,
				"default_schema_json": json.dumps({
					"memory_type": "requirement|decision|api_contract|spec|note",
					"title": "string",
					"content": "string",
					"project": "string",
					"status": "draft|approved|deprecated",
					"stakeholders": ["string"],
					"related_docs": ["string"],
					"confidence": "number"
				}, indent=2),
				"default_capture_prompt": """Extract documentation and project-related information from the conversation.

Capture:
- Requirements or specifications
- Decisions made and their rationale
- API contracts or interfaces
- Project context and notes

Return a JSON object with the schema.""",
				"default_capture_stage": "conversation_end",
				"default_frequency": "conversation_end",
				"default_scope_type": "namespace",
				"default_indexing_mode": "both",
				"default_retrieval_mode": "hybrid",
				"recommended_model": "gpt-4",
				"recommended_provider": "openai"
			}
		]
		
		created = []
		for profile_data in default_profiles:
			if not frappe.db.exists("Memory Profile", profile_data["profile_name"]):
				profile = frappe.new_doc("Memory Profile")
				profile.update(profile_data)
				profile.insert()
				created.append(profile.profile_name)
		
		return created
