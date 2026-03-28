# Copyright (c) 2026, HUF and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_days

class MemoryRecord(Document):
	"""
	Canonical portable unit of memory in the HUF system.
	
	Replaces conversation-embedded JSON with a first-class memory
	storage system supporting scoped retrieval, indexing, and
	lifetime management.
	"""
	
	def before_insert(self):
		"""Set default values and validate on creation."""
		self.creation_timestamp = now_datetime()
		
		# Calculate expiration if TTL is set
		if self.ttl_days and not self.expiration_timestamp:
			self.expiration_timestamp = add_days(now_datetime(), self.ttl_days)
		
		# Validate confidence and importance are in valid range
		if self.confidence is not None and (self.confidence < 0 or self.confidence > 1):
			frappe.throw("Confidence must be between 0.0 and 1.0")
		
		if self.importance_score is not None and (self.importance_score < 0 or self.importance_score > 1):
			frappe.throw("Importance score must be between 0.0 and 1.0")
		
		# Validate effective dates
		if self.effective_from and self.effective_until:
			if self.effective_from > self.effective_until:
				frappe.throw("Effective From must be before Effective Until")
	
	def before_save(self):
		"""Update timestamps and validate state transitions."""
		# Update expiration if TTL changed
		if self.ttl_days and not self.expiration_timestamp:
			self.expiration_timestamp = add_days(now_datetime(), self.ttl_days)
		
		# Auto-archive expired records
		if self.expiration_timestamp and now_datetime() > self.expiration_timestamp:
			if self.status == "active":
				self.status = "expired"
	
	def on_update(self):
		"""Handle post-update operations."""
		# Update the superseded record if set
		if self.supersedes_memory_record and self.status == "active":
			frappe.db.set_value("Memory Record", self.supersedes_memory_record, "status", "superseded")
	
	def record_retrieval(self):
		"""
		Increment retrieval count and update last retrieved timestamp.
		Called by retrieval service when this memory is fetched.
		"""
		self.retrieval_count = (self.retrieval_count or 0) + 1
		self.last_retrieved_at = now_datetime()
		self.db_update()
		frappe.db.commit()
	
	def mark_indexed(self, backend: str, indexed_at=None):
		"""
		Mark this record as indexed.
		
		Args:
			backend: The index backend used (fts, vector, both)
			indexed_at: Optional timestamp, defaults to now
		"""
		if indexed_at is None:
			indexed_at = now_datetime()
		
		if backend == "fts":
			self.fts_indexed = 1
		elif backend == "vector":
			self.vector_indexed = 1
		elif backend == "both":
			self.fts_indexed = 1
			self.vector_indexed = 1
		
		self.last_indexed_at = indexed_at
		self.index_backend = backend if backend != "both" else "sqlite_fts"
		self.db_update()
		frappe.db.commit()
	
	def is_valid(self) -> bool:
		"""
		Check if this memory record is currently valid and active.
		
		Returns:
			True if the record is valid for retrieval
		"""
		# Check status
		if self.status not in ["active"]:
			return False
		
		# Check effective dates
		now = now_datetime()
		if self.effective_from and now < self.effective_from:
			return False
		if self.effective_until and now > self.effective_until:
			return False
		if self.expiration_timestamp and now > self.expiration_timestamp:
			return False
		
		return True
	
	def is_in_scope(self, scope_type: str, scope_key: str) -> bool:
		"""
		Check if this memory is accessible within the given scope.
		
		Args:
			scope_type: The scope type to check against
			scope_key: The scope key to check against
			
		Returns:
			True if accessible in the given scope
		"""
		# Exact scope match
		if self.scope_type == scope_type and self.scope_key == scope_key:
			return True
		
		# Wider scope access (global is always accessible)
		if self.scope_type == "global":
			return True
		
		# Agent scope is accessible to conversations/runs of that agent
		if self.scope_type == "agent" and scope_type in ["conversation", "run"]:
			# Check if the scope belongs to this agent
			return self._scope_belongs_to_agent(scope_key, self.scope_key)
		
		# Namespace scope - check if scope_key is in namespace
		if self.scope_type == "namespace":
			return self._scope_in_namespace(scope_key, self.scope_key)
		
		return False
	
	def _scope_belongs_to_agent(self, scope_key: str, agent_scope_key: str) -> bool:
		"""Check if a conversation/run scope belongs to an agent."""
		# This would need implementation based on how scope_keys are constructed
		# Typically conversation scope_key contains agent ID
		return agent_scope_key in scope_key
	
	def _scope_in_namespace(self, scope_key: str, namespace_key: str) -> bool:
		"""Check if a scope is within a namespace."""
		# Implementation depends on namespace structure
		return scope_key.startswith(namespace_key)
	
	@staticmethod
	def get_active_memories(
		scope_type: str,
		scope_key: str,
		memory_type: str = None,
		agent: str = None,
		limit: int = 100
	):
		"""
		Get active memories for a given scope.
		
		Args:
			scope_type: The scope type to filter by
			scope_key: The scope key to filter by
			memory_type: Optional memory type filter
			agent: Optional agent filter
			limit: Maximum number of records to return
			
		Returns:
			List of MemoryRecord documents
		"""
		filters = {
			"status": "active"
		}
		
		if memory_type:
			filters["memory_type"] = memory_type
		if agent:
			filters["agent"] = agent
		
		# Get all active memories and filter by scope
		records = frappe.get_all(
			"Memory Record",
			filters=filters,
			fields=["name"],
			limit=limit * 2  # Get more for scope filtering
		)
		
		result = []
		for r in records:
			doc = frappe.get_doc("Memory Record", r.name)
			if doc.is_valid() and doc.is_in_scope(scope_type, scope_key):
				result.append(doc)
				if len(result) >= limit:
					break
		
		return result


@frappe.whitelist()
def record_retrieval(memory_record_name: str):
	"""
	API endpoint to record a memory retrieval.
	
	Args:
		memory_record_name: The name of the memory record
	"""
	try:
		doc = frappe.get_doc("Memory Record", memory_record_name)
		doc.record_retrieval()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Failed to record retrieval for {memory_record_name}: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def expire_old_memories():
	"""
	Batch job to mark expired memories based on expiration_timestamp.
	"""
	now = now_datetime()
	
	expired = frappe.get_all(
		"Memory Record",
		filters={
			"status": "active",
			"expiration_timestamp": ["<", now]
		},
		fields=["name"]
	)
	
	count = 0
	for r in expired:
		try:
			frappe.db.set_value("Memory Record", r.name, "status", "expired")
			count += 1
		except Exception as e:
			frappe.log_error(f"Failed to expire memory {r.name}: {str(e)}")
	
	frappe.db.commit()
	return {"expired_count": count}
