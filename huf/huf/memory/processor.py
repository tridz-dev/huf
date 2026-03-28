# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Memory Capture Processor Module

Main processor for HUF Memory System capture pipeline.
Orchestrates triggers, capture modes, and memory record creation.

The processor:
1. Evaluates triggers to determine if capture should run
2. Executes the appropriate capture mode
3. Creates/updates Memory Record documents
4. Handles indexing (FTS, vector)
5. Provides observability/logging
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from huf.memory.capture import (
	get_capture_mode,
	CaptureMode,
	CaptureModeType
)
from huf.memory.triggers import (
	get_trigger,
	TriggerManager,
	TriggerResult,
	TriggerType
)


class CaptureProcessor:
	"""
	Main processor for memory capture pipeline.
	
	Orchestrates the entire capture flow:
	- Trigger evaluation
	- Capture mode execution
	- Memory record persistence
	- Indexing
	- Observability
	"""
	
	def __init__(self, policy_config: Optional[Dict[str, Any]] = None):
		"""
		Initialize the capture processor.
		
		Args:
			policy_config: Memory policy configuration dict
		"""
		self.policy_config = policy_config or {}
		self.trigger_manager = TriggerManager()
		self._setup_triggers()
		
	def _setup_triggers(self):
		"""Setup triggers based on policy configuration."""
		trigger_configs = self.policy_config.get("triggers", [])
		
		# If no triggers specified, add default every_run trigger
		if not trigger_configs:
			trigger_configs = [{"trigger_type": "every_run"}]
		
		for trigger_config in trigger_configs:
			try:
				trigger = get_trigger(trigger_config)
				self.trigger_manager.add_trigger(trigger)
			except ValueError as e:
				frappe.log_error(f"Invalid trigger config: {str(e)}", "Memory Processor")
				
	def process(
		self,
		context: Dict[str, Any],
		force: bool = False
	) -> Dict[str, Any]:
		"""
		Main entry point for memory capture processing.
		
		Args:
			context: Capture context containing conversation, run, etc.
			force: Force capture regardless of triggers
			
		Returns:
			Dict with capture results and metadata
		"""
		start_time = datetime.now()
		
		# Initialize result structure
		result = {
			"capture_triggered": False,
			"capture_mode": None,
			"trigger_type": None,
			"trigger_reason": None,
			"records_created": 0,
			"records_updated": 0,
			"records_skipped": 0,
			"validation_errors": [],
			"index_jobs_started": 0,
			"latency_ms": 0,
			"error": None
		}
		
		try:
			# Step 1: Evaluate triggers (unless forced)
			trigger_result = None
			if not force:
				trigger_result = self.trigger_manager.should_capture(context)
				
				if not trigger_result:
					result["capture_triggered"] = False
					result["latency_ms"] = self._calculate_latency(start_time)
					return result
				
				result["trigger_type"] = trigger_result.trigger_type
				result["trigger_reason"] = trigger_result.reason
			else:
				result["trigger_type"] = "manual_forced"
				result["trigger_reason"] = "Capture forced by caller"
			
			result["capture_triggered"] = True
			
			# Step 2: Execute capture mode
			capture_result = self._execute_capture(context)
			
			if capture_result.get("error"):
				result["error"] = capture_result["error"]
				result["latency_ms"] = self._calculate_latency(start_time)
				return result
			
			# Step 3: Create/update memory records
			records_result = self._persist_memory_records(
				capture_result.get("payload", {}),
				context,
				trigger_result
			)
			
			result["records_created"] = records_result.get("created", 0)
			result["records_updated"] = records_result.get("updated", 0)
			result["records_skipped"] = records_result.get("skipped", 0)
			result["validation_errors"] = records_result.get("errors", [])
			result["capture_mode"] = capture_result.get("mode_type")
			
			# Step 4: Start indexing jobs if configured
			if records_result.get("created") or records_result.get("updated"):
				index_result = self._start_indexing(records_result.get("record_ids", []))
				result["index_jobs_started"] = index_result.get("jobs_started", 0)
			
			# Step 5: Update run observability fields
			self._update_run_observability(context, result)
			
		except Exception as e:
			error_msg = f"Capture processing failed: {str(e)}"
			frappe.log_error(error_msg, "Memory Capture Processor")
			result["error"] = error_msg
			
		finally:
			result["latency_ms"] = self._calculate_latency(start_time)
			
		return result
		
	def _execute_capture(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Execute the configured capture mode.
		
		Args:
			context: Capture context
			
		Returns:
			Dict with capture results
		"""
		capture_config = self.policy_config.get("capture", {})
		capture_mode_id = capture_config.get("capture_mode", "post_async")
		
		try:
			capture_mode = get_capture_mode(capture_config)
			
			# Validate capture mode config
			if not capture_mode.validate():
				return {
					"error": "Capture mode validation failed",
					"mode_type": capture_mode_id
				}
			
			# Execute capture
			result = capture_mode.execute(context)
			result["mode_type"] = capture_mode_id
			
			return result
			
		except Exception as e:
			frappe.log_error(f"Capture execution failed: {str(e)}", "Memory Capture")
			return {
				"error": str(e),
				"mode_type": capture_mode_id
			}
			
	def _persist_memory_records(
		self,
		payload: Dict[str, Any],
		context: Dict[str, Any],
		trigger_result: Optional[TriggerResult]
	) -> Dict[str, Any]:
		"""
		Create or update memory records from capture payload.
		
		Args:
			payload: Structured memory data from capture
			context: Capture context
			trigger_result: The trigger that fired
			
		Returns:
			Dict with persistence results
		"""
		result = {
			"created": 0,
			"updated": 0,
			"skipped": 0,
			"errors": [],
			"record_ids": []
		}
		
		if not payload:
			result["skipped"] = 1
			return result
		
		# Determine scope
		scope_type = self.policy_config.get("scope_type", "conversation")
		scope_key = self._resolve_scope_key(scope_type, context)
		
		# Check if we should update existing or create new
		allow_update = self.policy_config.get("allow_update_existing", True)
		allow_merge = self.policy_config.get("allow_merge", False)
		
		try:
			# Build memory record data
			record_data = self._build_memory_record(
				payload,
				context,
				trigger_result,
				scope_type,
				scope_key
			)
			
			# Check for existing record to update
			existing_id = None
			if allow_update:
				existing_id = self._find_existing_record(
					scope_type,
					scope_key,
					record_data.get("memory_type"),
					record_data.get("schema_name")
				)
			
			if existing_id and allow_update:
				# Update existing record
				if allow_merge:
					self._merge_memory_record(existing_id, record_data)
				else:
					self._update_memory_record(existing_id, record_data)
				result["updated"] += 1
				result["record_ids"].append(existing_id)
			else:
				# Create new record
				record_id = self._create_memory_record(record_data)
				if record_id:
					result["created"] += 1
					result["record_ids"].append(record_id)
					
		except Exception as e:
			error_msg = f"Failed to persist memory record: {str(e)}"
			result["errors"].append(error_msg)
			frappe.log_error(error_msg, "Memory Persistence")
			
		return result
		
	def _build_memory_record(
		self,
		payload: Dict[str, Any],
		context: Dict[str, Any],
		trigger_result: Optional[TriggerResult],
		scope_type: str,
		scope_key: str
	) -> Dict[str, Any]:
		"""Build memory record data from capture payload."""
		conversation = context.get("conversation", {})
		run = context.get("run", {})
		
		# Determine memory type from policy or payload
		memory_type = payload.get("memory_type") or self.policy_config.get(
			"default_memory_type", "observation"
		)
		
		# Build the record
		record = {
			"doctype": "Agent Memory Record",
			"title": payload.get("title", self._generate_title(payload, memory_type)),
			"agent": context.get("agent_id"),
			"conversation": context.get("conversation_id"),
			"run": context.get("run_id"),
			"source_type": "conversation",
			"producer_mode": self.policy_config.get("capture", {}).get("capture_mode", "post_async"),
			"memory_type": memory_type,
			"schema_name": self.policy_config.get("memory_profile"),
			"data_json": frappe.as_json(payload.get("data", payload)),
			"summary_text": payload.get("summary", ""),
			"raw_context_excerpt": self._extract_context_excerpt(context),
			"scope_type": scope_type,
			"scope_key": scope_key,
			"visibility": self.policy_config.get("visibility", "private"),
			"status": "active",
			"confidence": payload.get("confidence", 0.8),
			"importance_score": payload.get("importance", 0.5),
			"ttl_days": self.policy_config.get("ttl_days"),
			"created_from_turn_count": conversation.get("turn_count", 0),
			"tags": payload.get("tags", []),
			"metadata_json": frappe.as_json({
				"trigger_type": trigger_result.trigger_type if trigger_result else None,
				"trigger_reason": trigger_result.reason if trigger_result else None,
				"capture_timestamp": datetime.now().isoformat()
			}),
			"fts_indexed": False,
			"vector_indexed": False
		}
		
		return record
		
	def _create_memory_record(self, record_data: Dict[str, Any]) -> Optional[str]:
		"""Create a new memory record document."""
		try:
			doc = frappe.get_doc(record_data)
			doc.insert(ignore_permissions=True)
			return doc.name
		except Exception as e:
			frappe.log_error(f"Failed to create memory record: {str(e)}", "Memory Persistence")
			return None
			
	def _update_memory_record(self, record_id: str, record_data: Dict[str, Any]):
		"""Update an existing memory record."""
		try:
			doc = frappe.get_doc("Agent Memory Record", record_id)
			
			# Update fields
			doc.data_json = record_data.get("data_json", doc.data_json)
			doc.summary_text = record_data.get("summary_text", doc.summary_text)
			doc.confidence = record_data.get("confidence", doc.confidence)
			doc.importance_score = record_data.get("importance_score", doc.importance_score)
			doc.tags = record_data.get("tags", doc.tags)
			
			doc.save(ignore_permissions=True)
			
		except Exception as e:
			frappe.log_error(f"Failed to update memory record {record_id}: {str(e)}", "Memory Persistence")
			
	def _merge_memory_record(self, record_id: str, record_data: Dict[str, Any]):
		"""Merge new data into existing memory record."""
		try:
			doc = frappe.get_doc("Agent Memory Record", record_id)
			
			# Parse existing data
			import json
			try:
				existing_data = json.loads(doc.data_json or "{}")
			except:
				existing_data = {}
			
			# Parse new data
			try:
				new_data = json.loads(record_data.get("data_json", "{}"))
			except:
				new_data = {}
			
			# Merge (new data takes precedence)
			merged_data = {**existing_data, **new_data}
			doc.data_json = json.dumps(merged_data)
			
			# Update other fields
			if record_data.get("summary_text"):
				doc.summary_text = record_data.get("summary_text")
			
			doc.save(ignore_permissions=True)
			
		except Exception as e:
			frappe.log_error(f"Failed to merge memory record {record_id}: {str(e)}", "Memory Persistence")
		
	def _find_existing_record(
		self,
		scope_type: str,
		scope_key: str,
		memory_type: Optional[str],
		schema_name: Optional[str]
	) -> Optional[str]:
		"""Find an existing memory record to update."""
		filters = {
			"scope_type": scope_type,
			"scope_key": scope_key,
			"status": "active"
		}
		
		if memory_type:
			filters["memory_type"] = memory_type
		if schema_name:
			filters["schema_name"] = schema_name
		
		# Get most recent matching record
		results = frappe.get_all(
			"Agent Memory Record",
			filters=filters,
			order_by="creation desc",
			limit_page_length=1
		)
		
		return results[0].name if results else None
		
	def _resolve_scope_key(self, scope_type: str, context: Dict[str, Any]) -> str:
		"""Resolve the scope key based on scope type."""
		if scope_type == "conversation":
			return context.get("conversation_id", "")
		elif scope_type == "user":
			return context.get("user_id", frappe.session.user)
		elif scope_type == "agent":
			return context.get("agent_id", "")
		elif scope_type == "namespace":
			return self.policy_config.get("namespace_key", "default")
		elif scope_type == "global":
			return "global"
		return ""
		
	def _generate_title(self, payload: Dict[str, Any], memory_type: str) -> str:
		"""Generate a title for the memory record."""
		if payload.get("title"):
			return payload.get("title")
		
		# Generate based on memory type and content
		timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
		
		type_labels = {
			"profile": f"User Profile - {timestamp}",
			"preference": f"Preference - {timestamp}",
			"fact": f"Fact - {timestamp}",
			"plan": f"Plan - {timestamp}",
			"observation": f"Observation - {timestamp}",
			"insight": f"Insight - {timestamp}",
			"domain_object": f"Context - {timestamp}"
		}
		
		return type_labels.get(memory_type, f"Memory - {timestamp}")
		
	def _extract_context_excerpt(self, context: Dict[str, Any], max_length: int = 1000) -> str:
		"""Extract a text excerpt from conversation context."""
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
		
	def _start_indexing(self, record_ids: List[str]) -> Dict[str, Any]:
		"""Start indexing jobs for memory records."""
		result = {"jobs_started": 0}
		
		enable_fts = self.policy_config.get("enable_fts_index", True)
		enable_vector = self.policy_config.get("enable_vector_index", False)
		
		if not record_ids:
			return result
		
		try:
			if enable_fts:
				# Enqueue FTS indexing job
				frappe.enqueue(
					method="huf.memory.indexing.index_records_fts",
					queue="default",
					record_ids=record_ids,
					timeout=300
				)
				result["jobs_started"] += 1
				result["fts_queued"] = True
			
			if enable_vector:
				# Enqueue vector indexing job
				frappe.enqueue(
					method="huf.memory.indexing.index_records_vector",
					queue="default",
					record_ids=record_ids,
					timeout=300
				)
				result["jobs_started"] += 1
				result["vector_queued"] = True
					
		except Exception as e:
			frappe.log_error(f"Failed to start indexing: {str(e)}", "Memory Indexing")
			
		return result
		
	def _update_run_observability(self, context: Dict[str, Any], result: Dict[str, Any]):
		"""Update agent run with memory capture observability fields."""
		run_id = context.get("run_id")
		if not run_id or not frappe.db.exists("Agent Run", run_id):
			return
		
		try:
			frappe.db.set_value("Agent Run", run_id, {
				"memory_capture_triggered": result["capture_triggered"],
				"memory_capture_mode": result.get("capture_mode"),
				"memory_records_created": result.get("records_created", 0),
				"memory_records_updated": result.get("records_updated", 0),
				"memory_records_skipped": result.get("records_skipped", 0),
				"memory_capture_latency_ms": result.get("latency_ms", 0)
			})
		except Exception as e:
			frappe.log_error(f"Failed to update run observability: {str(e)}", "Memory Processor")
			
	def _calculate_latency(self, start_time: datetime) -> int:
		"""Calculate elapsed time in milliseconds."""
		elapsed = (datetime.now() - start_time).total_seconds()
		return int(elapsed * 1000)


class BatchCaptureProcessor:
	"""
	Processor for batch memory capture operations.
	
	Used for scheduled consolidation, deduplication, etc.
	"""
	
	def __init__(self, config: Optional[Dict[str, Any]] = None):
		self.config = config or {}
		
	def process_batch(
		self,
		record_filters: Dict[str, Any],
		operation: str = "consolidate"
	) -> Dict[str, Any]:
		"""
		Process a batch of memory records.
		
		Args:
			record_filters: Filters for selecting records
			operation: Operation to perform (consolidate, dedupe, archive)
			
		Returns:
			Dict with batch operation results
		"""
		result = {
			"operation": operation,
			"records_processed": 0,
			"records_affected": 0,
			"errors": []
		}
		
		try:
			# Get records matching filters
			records = frappe.get_all(
				"Agent Memory Record",
				filters=record_filters,
				fields=["name", "data_json", "memory_type", "scope_key"]
			)
			
			result["records_processed"] = len(records)
			
			if operation == "consolidate":
				affected = self._consolidate_records(records)
				result["records_affected"] = affected
			elif operation == "dedupe":
				affected = self._deduplicate_records(records)
				result["records_affected"] = affected
			elif operation == "archive":
				affected = self._archive_records(records)
				result["records_affected"] = affected
					
		except Exception as e:
			result["errors"].append(str(e))
			frappe.log_error(f"Batch operation failed: {str(e)}", "Memory Batch Processor")
			
		return result
		
	def _consolidate_records(self, records: List[Dict]) -> int:
		"""Consolidate similar memory records."""
		# Group by memory type and scope
		groups = {}
		for record in records:
			key = (record.get("memory_type"), record.get("scope_key"))
			if key not in groups:
				groups[key] = []
			groups[key].append(record)
		
		affected = 0
		for (mem_type, scope), group_records in groups.items():
			if len(group_records) > 1:
				# Mark older records as superseded
				sorted_records = sorted(group_records, key=lambda r: r.get("creation", ""), reverse=True)
				latest = sorted_records[0]
				
				for old_record in sorted_records[1:]:
					try:
						frappe.db.set_value(
							"Agent Memory Record",
							old_record["name"],
							{
								"status": "superseded",
								"supersedes_memory_record": latest["name"]
							}
						)
						affected += 1
					except Exception as e:
						frappe.log_error(f"Consolidation failed: {str(e)}", "Memory Consolidation")
						
		return affected
		
	def _deduplicate_records(self, records: List[Dict]) -> int:
		"""Deduplicate memory records based on content hash."""
		import hashlib
		
		seen_hashes = set()
		affected = 0
		
		for record in records:
			data = record.get("data_json", "")
			content_hash = hashlib.md5(data.encode()).hexdigest()
			
			if content_hash in seen_hashes:
				# Duplicate found - archive it
				try:
					frappe.db.set_value(
						"Agent Memory Record",
						record["name"],
						"status", "archived"
					)
					affected += 1
				except Exception as e:
					frappe.log_error(f"Deduplication failed: {str(e)}", "Memory Deduplication")
			else:
				seen_hashes.add(content_hash)
				
		return affected
		
	def _archive_records(self, records: List[Dict]) -> int:
		"""Archive memory records."""
		affected = 0
		
		for record in records:
			try:
				frappe.db.set_value(
					"Agent Memory Record",
					record["name"],
					"status", "archived"
				)
				affected += 1
			except Exception as e:
				frappe.log_error(f"Archival failed: {str(e)}", "Memory Archive")
				
		return affected


# Convenience functions for common operations

def capture_memory(
	context: Dict[str, Any],
	policy_config: Optional[Dict[str, Any]] = None,
	force: bool = False
) -> Dict[str, Any]:
	"""
	Convenience function to capture memory with a single call.
	
	Args:
		context: Capture context
		policy_config: Optional policy configuration
		force: Force capture regardless of triggers
		
	Returns:
		Capture result dict
	"""
	processor = CaptureProcessor(policy_config)
	return processor.process(context, force=force)


def capture_memory_async(
	context: Dict[str, Any],
	policy_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
	"""
	Enqueue memory capture as a background job.
	
	Args:
		context: Capture context
		policy_config: Policy configuration
		
	Returns:
		Job enqueue result
	"""
	try:
		job = frappe.enqueue(
			method="huf.memory.processor.capture_memory",
			queue="memory_capture",
			context=context,
			policy_config=policy_config,
			timeout=300
		)
		
		return {
			"enqueued": True,
			"job_id": job.id if hasattr(job, 'id') else str(job),
			"message": "Memory capture queued"
		}
	except Exception as e:
		return {
			"enqueued": False,
			"error": str(e)
		}


def process_conversation_end(
	conversation_id: str,
	policy_config: Optional[Dict[str, Any]] = None,
	end_strategy: str = "manual_close"
) -> Dict[str, Any]:
	"""
	Process memory capture for conversation end.
	
	Args:
		conversation_id: The conversation that ended
		policy_config: Policy configuration
		end_strategy: How the conversation ended
		
	Returns:
		Capture result dict
	"""
	# Load conversation data
	if not frappe.db.exists("Agent Conversation", conversation_id):
		return {"error": f"Conversation {conversation_id} not found"}
	
	conversation = frappe.get_doc("Agent Conversation", conversation_id)
	
	# Build context
	context = {
		"conversation_id": conversation_id,
		"agent_id": conversation.agent,
		"user_id": conversation.user,
		"conversation": {
			"messages": conversation.get_messages() if hasattr(conversation, 'get_messages') else [],
			"turn_count": conversation.get("turn_count", 0),
			"last_activity_at": conversation.modified
		},
		"end_event": {
			"strategy": end_strategy,
			"timestamp": datetime.now().isoformat(),
			"reason": f"Conversation ended via {end_strategy}"
		}
	}
	
	# Ensure conversation_end trigger is in policy
	if policy_config:
		triggers = policy_config.get("triggers", [])
		has_end_trigger = any(
			t.get("trigger_type") == "conversation_end" for t in triggers
		)
		if not has_end_trigger:
			triggers.append({
				"trigger_type": "conversation_end",
				"end_strategy": end_strategy
			})
			policy_config["triggers"] = triggers
	
	return capture_memory(context, policy_config, force=True)


# Background job handlers for async processing
def process_scheduled_consolidation(
	scope_filter: Optional[Dict] = None,
	operation: str = "consolidate"
):
	"""
	Background job handler for scheduled memory consolidation.
	"""
	processor = BatchCaptureProcessor()
	
	filters = scope_filter or {
		"status": "active",
		"creation": ["<", frappe.utils.add_days(frappe.utils.now(), -7)]
	}
	
	result = processor.process_batch(filters, operation)
	
	frappe.logger().info(f"Scheduled consolidation completed: {result}")
	
	return result