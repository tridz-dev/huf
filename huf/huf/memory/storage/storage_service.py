"""
HUF Memory System - Storage Service

Canonical storage for Memory Records in the DocType system.
This module provides the primary interface for creating, reading, updating,
and deleting Memory Records in the MariaDB-backed DocType storage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import frappe
from frappe.model.document import Document

if TYPE_CHECKING:
    from .index_backend import IndexResult


class SourceType(str, Enum):
    """Source of the memory record."""
    CONVERSATION = "conversation"
    RUN = "run"
    MANUAL = "manual"
    EVENT = "event"
    SCHEDULED = "scheduled"
    IMPORTED = "imported"


class ProducerMode(str, Enum):
    """Who/what produced the memory record."""
    MAIN_AGENT = "main_agent"
    MEMORY_AGENT = "memory_agent"
    POST_RUN_LLM = "post_run_llm"
    RULES_ONLY = "rules_only"
    MANUAL = "manual"


class MemoryType(str, Enum):
    """Type/classification of memory content."""
    PROFILE = "profile"
    SESSION_STATE = "session_state"
    PREFERENCE = "preference"
    FACT = "fact"
    PLAN = "plan"
    OBSERVATION = "observation"
    INSIGHT = "insight"
    DOMAIN_OBJECT = "domain_object"
    CUSTOM = "custom"


class ScopeType(str, Enum):
    """Visibility scope of the memory record."""
    CONVERSATION = "conversation"
    USER = "user"
    AGENT = "agent"
    NAMESPACE = "namespace"
    GLOBAL = "global"


class Visibility(str, Enum):
    """Sharing visibility level."""
    PRIVATE = "private"
    SHARED_WITH_AGENT = "shared_with_agent"
    SHARED_WITH_NAMESPACE = "shared_with_namespace"
    GLOBAL = "global"


class MemoryStatus(str, Enum):
    """Lifecycle status of the memory record."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    ERROR = "error"


class IndexBackend(str, Enum):
    """Available indexing backends."""
    NONE = "none"
    SQLITE_FTS = "sqlite_fts"
    SQLITE_VEC = "sqlite_vec"
    PGVECTOR = "pgvector"
    CUSTOM = "custom"


class MemoryRecord:
    """
    Canonical memory record data class.
    
    This represents the structured data before it becomes a DocType document.
    It provides a type-safe interface for working with memory records.
    """
    
    def __init__(
        self,
        title: str,
        data_json: dict[str, Any],
        agent: Optional[str] = None,
        conversation: Optional[str] = None,
        run: Optional[str] = None,
        source_type: SourceType = SourceType.MANUAL,
        producer_mode: ProducerMode = ProducerMode.MANUAL,
        memory_type: MemoryType = MemoryType.CUSTOM,
        schema_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        summary_text: Optional[str] = None,
        raw_context_excerpt: Optional[str] = None,
        scope_type: ScopeType = ScopeType.CONVERSATION,
        scope_key: Optional[str] = None,
        visibility: Visibility = Visibility.PRIVATE,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        confidence: float = 1.0,
        importance_score: float = 0.5,
        ttl_days: Optional[int] = None,
        effective_from: Optional[datetime] = None,
        effective_until: Optional[datetime] = None,
        supersedes_memory_record: Optional[str] = None,
        created_from_turn_count: Optional[int] = None,
        tags: Optional[list[str]] = None,
        metadata_json: Optional[dict[str, Any]] = None,
        enable_fts_index: bool = True,
        enable_vector_index: bool = False,
        index_backend: IndexBackend = IndexBackend.NONE,
        name: Optional[str] = None,
    ):
        self.name = name or self._generate_name()
        self.title = title
        self.agent = agent
        self.conversation = conversation
        self.run = run
        self.source_type = source_type
        self.producer_mode = producer_mode
        self.memory_type = memory_type
        self.schema_name = schema_name
        self.profile_name = profile_name
        self.data_json = data_json
        self.summary_text = summary_text or title
        self.raw_context_excerpt = raw_context_excerpt
        self.scope_type = scope_type
        self.scope_key = scope_key
        self.visibility = visibility
        self.status = status
        self.confidence = confidence
        self.importance_score = importance_score
        self.ttl_days = ttl_days
        self.effective_from = effective_from or datetime.now()
        self.effective_until = effective_until
        self.supersedes_memory_record = supersedes_memory_record
        self.created_from_turn_count = created_from_turn_count
        self.tags = tags or []
        self.metadata_json = metadata_json or {}
        self.enable_fts_index = enable_fts_index
        self.enable_vector_index = enable_vector_index
        self.index_backend = index_backend
        self.fts_indexed = False
        self.vector_indexed = False
        self.last_indexed_at: Optional[datetime] = None
        self.last_retrieved_at: Optional[datetime] = None
        self.retrieval_count = 0
        self.creation = datetime.now()
        self.modified = datetime.now()
    
    def _generate_name(self) -> str:
        """Generate a unique name/hash for the record."""
        timestamp = datetime.now().isoformat()
        random_component = hashlib.sha256(
            f"{timestamp}{id(self)}".encode()
        ).hexdigest()[:16]
        return f"MEM-{random_component}"
    
    def to_doc(self) -> Document:
        """Convert MemoryRecord to a Frappe Document."""
        if frappe.db.exists("Memory Record", self.name):
            doc = frappe.get_doc("Memory Record", self.name)
        else:
            doc = frappe.new_doc("Memory Record")
        
        doc.update({
            "name": self.name,
            "title": self.title,
            "agent": self.agent,
            "conversation": self.conversation,
            "run": self.run,
            "source_type": self.source_type.value,
            "producer_mode": self.producer_mode.value,
            "memory_type": self.memory_type.value,
            "schema_name": self.schema_name,
            "profile_name": self.profile_name,
            "data_json": json.dumps(self.data_json),
            "summary_text": self.summary_text,
            "raw_context_excerpt": self.raw_context_excerpt,
            "scope_type": self.scope_type.value,
            "scope_key": self.scope_key,
            "visibility": self.visibility.value,
            "status": self.status.value,
            "confidence": self.confidence,
            "importance_score": self.importance_score,
            "ttl_days": self.ttl_days,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "supersedes_memory_record": self.supersedes_memory_record,
            "created_from_turn_count": self.created_from_turn_count,
            "tags": ",".join(self.tags) if self.tags else None,
            "metadata_json": json.dumps(self.metadata_json) if self.metadata_json else None,
            "fts_indexed": self.fts_indexed,
            "vector_indexed": self.vector_indexed,
            "index_backend": self.index_backend.value,
            "last_indexed_at": self.last_indexed_at,
            "last_retrieved_at": self.last_retrieved_at,
            "retrieval_count": self.retrieval_count,
        })
        
        return doc
    
    @classmethod
    def from_doc(cls, doc: Document) -> MemoryRecord:
        """Create MemoryRecord from a Frappe Document."""
        record = cls.__new__(cls)
        record.name = doc.name
        record.title = doc.title
        record.agent = doc.agent
        record.conversation = doc.conversation
        record.run = doc.run
        record.source_type = SourceType(doc.source_type)
        record.producer_mode = ProducerMode(doc.producer_mode)
        record.memory_type = MemoryType(doc.memory_type)
        record.schema_name = doc.schema_name
        record.profile_name = doc.profile_name
        record.data_json = json.loads(doc.data_json) if doc.data_json else {}
        record.summary_text = doc.summary_text
        record.raw_context_excerpt = doc.raw_context_excerpt
        record.scope_type = ScopeType(doc.scope_type)
        record.scope_key = doc.scope_key
        record.visibility = Visibility(doc.visibility)
        record.status = MemoryStatus(doc.status)
        record.confidence = doc.confidence
        record.importance_score = doc.importance_score
        record.ttl_days = doc.ttl_days
        record.effective_from = doc.effective_from
        record.effective_until = doc.effective_until
        record.supersedes_memory_record = doc.supersedes_memory_record
        record.created_from_turn_count = doc.created_from_turn_count
        record.tags = doc.tags.split(",") if doc.tags else []
        record.metadata_json = json.loads(doc.metadata_json) if doc.metadata_json else {}
        record.fts_indexed = doc.fts_indexed
        record.vector_indexed = doc.vector_indexed
        record.index_backend = IndexBackend(doc.index_backend) if doc.index_backend else IndexBackend.NONE
        record.last_indexed_at = doc.last_indexed_at
        record.last_retrieved_at = doc.last_retrieved_at
        record.retrieval_count = doc.retrieval_count
        record.creation = doc.creation
        record.modified = doc.modified
        
        return record
    
    def is_expired(self) -> bool:
        """Check if the memory record has expired."""
        if self.status == MemoryStatus.EXPIRED:
            return True
        if self.effective_until and datetime.now() > self.effective_until:
            return True
        if self.ttl_days:
            expiry_date = self.creation + timedelta(days=self.ttl_days)
            if datetime.now() > expiry_date:
                return True
        return False
    
    def can_index(self) -> bool:
        """Check if this record should be indexed based on policy."""
        return (
            self.status == MemoryStatus.ACTIVE
            and not self.is_expired()
            and (self.enable_fts_index or self.enable_vector_index)
        )
    
    def mark_retrieved(self) -> None:
        """Mark the record as retrieved."""
        self.last_retrieved_at = datetime.now()
        self.retrieval_count += 1


class MemoryStorage:
    """
    Canonical storage interface for Memory Records.
    
    This class provides CRUD operations and queries for Memory Records
    stored in the MariaDB DocType system. It is the source of truth
    for all memory data.
    """
    
    def __init__(self):
        self.doctype = "Memory Record"
    
    def create(self, record: MemoryRecord, index_callback: Optional[callable] = None) -> MemoryRecord:
        """
        Create a new Memory Record in canonical storage.
        
        Args:
            record: The MemoryRecord to store
            index_callback: Optional callback to trigger indexing
            
        Returns:
            The stored MemoryRecord (with name assigned if new)
        """
        doc = record.to_doc()
        doc.insert(ignore_permissions=True)
        
        # Update record with assigned values
        record.name = doc.name
        record.creation = doc.creation
        record.modified = doc.modified
        
        # Trigger indexing if callback provided and record should be indexed
        if index_callback and record.can_index():
            try:
                index_callback(record)
            except Exception as e:
                frappe.log_error(f"Memory indexing failed for {record.name}: {str(e)}")
        
        return record
    
    def get(self, name: str) -> Optional[MemoryRecord]:
        """
        Retrieve a Memory Record by name.
        
        Args:
            name: The record name/ID
            
        Returns:
            MemoryRecord if found, None otherwise
        """
        if not frappe.db.exists(self.doctype, name):
            return None
        
        doc = frappe.get_doc(self.doctype, name)
        record = MemoryRecord.from_doc(doc)
        
        # Update retrieval tracking
        frappe.db.set_value(
            self.doctype,
            name,
            {
                "last_retrieved_at": datetime.now(),
                "retrieval_count": record.retrieval_count + 1
            },
            update_modified=False
        )
        
        return record
    
    def update(
        self, 
        record: MemoryRecord, 
        index_callback: Optional[callable] = None
    ) -> MemoryRecord:
        """
        Update an existing Memory Record.
        
        Args:
            record: The MemoryRecord with updated values
            index_callback: Optional callback to trigger re-indexing
            
        Returns:
            The updated MemoryRecord
        """
        if not frappe.db.exists(self.doctype, record.name):
            raise ValueError(f"Memory Record {record.name} not found")
        
        record.modified = datetime.now()
        doc = record.to_doc()
        doc.save(ignore_permissions=True)
        
        # Trigger re-indexing if callback provided and record should be indexed
        if index_callback and record.can_index():
            try:
                index_callback(record)
            except Exception as e:
                frappe.log_error(f"Memory re-indexing failed for {record.name}: {str(e)}")
        
        return record
    
    def delete(self, name: str, index_callback: Optional[callable] = None) -> bool:
        """
        Delete a Memory Record.
        
        Args:
            name: The record name/ID to delete
            index_callback: Optional callback to remove from index
            
        Returns:
            True if deleted, False if not found
        """
        if not frappe.db.exists(self.doctype, name):
            return False
        
        # Remove from index first if callback provided
        if index_callback:
            try:
                index_callback(name)
            except Exception as e:
                frappe.log_error(f"Memory de-indexing failed for {name}: {str(e)}")
        
        frappe.delete_doc(self.doctype, name, ignore_permissions=True)
        return True
    
    def list(
        self,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 50,
        order_by: str = "modified desc"
    ) -> list[MemoryRecord]:
        """
        List Memory Records with optional filtering.
        
        Args:
            filters: Dict of field filters
            limit: Maximum records to return
            order_by: Sort order
            
        Returns:
            List of MemoryRecord objects
        """
        records = frappe.get_all(
            self.doctype,
            filters=filters,
            limit_page_length=limit,
            order_by=order_by
        )
        
        return [self.get(r.name) for r in records if self.get(r.name)]
    
    def find_by_scope(
        self,
        scope_type: ScopeType,
        scope_key: str,
        memory_type: Optional[MemoryType] = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        limit: int = 50
    ) -> list[MemoryRecord]:
        """
        Find Memory Records by scope.
        
        Args:
            scope_type: The scope type filter
            scope_key: The scope key filter
            memory_type: Optional memory type filter
            status: Status filter (default: active)
            limit: Maximum records to return
            
        Returns:
            List of matching MemoryRecord objects
        """
        filters = {
            "scope_type": scope_type.value,
            "scope_key": scope_key,
            "status": status.value
        }
        
        if memory_type:
            filters["memory_type"] = memory_type.value
        
        return self.list(filters=filters, limit=limit)
    
    def find_by_agent(
        self,
        agent: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 50
    ) -> list[MemoryRecord]:
        """
        Find Memory Records by agent.
        
        Args:
            agent: The agent name/ID
            memory_type: Optional memory type filter
            limit: Maximum records to return
            
        Returns:
            List of matching MemoryRecord objects
        """
        filters = {"agent": agent}
        
        if memory_type:
            filters["memory_type"] = memory_type.value
        
        return self.list(filters=filters, limit=limit)
    
    def find_by_conversation(
        self,
        conversation: str,
        limit: int = 100
    ) -> list[MemoryRecord]:
        """
        Find Memory Records by conversation.
        
        Args:
            conversation: The conversation name/ID
            limit: Maximum records to return
            
        Returns:
            List of matching MemoryRecord objects
        """
        return self.list(
            filters={"conversation": conversation},
            limit=limit,
            order_by="created_from_turn_count asc"
        )
    
    def find_by_tags(
        self,
        tags: list[str],
        match_all: bool = False,
        limit: int = 50
    ) -> list[MemoryRecord]:
        """
        Find Memory Records by tags.
        
        Args:
            tags: List of tags to match
            match_all: If True, record must have all tags; if False, any tag
            limit: Maximum records to return
            
        Returns:
            List of matching MemoryRecord objects
        """
        # Build SQL query for tag matching
        tag_conditions = []
        for tag in tags:
            tag_conditions.append(f"tags LIKE '%{tag}%'")
        
        if match_all:
            where_clause = " AND ".join(tag_conditions)
        else:
            where_clause = " OR ".join(tag_conditions)
        
        results = frappe.db.sql(
            f"""
            SELECT name FROM `tabMemory Record`
            WHERE {where_clause}
            AND status = 'active'
            ORDER BY modified DESC
            LIMIT {limit}
            """,
            as_dict=True
        )
        
        return [self.get(r.name) for r in results if self.get(r.name)]
    
    def expire_old_records(self) -> int:
        """
        Mark expired records based on TTL and effective_until dates.
        
        Returns:
            Number of records expired
        """
        now = datetime.now()
        count = 0
        
        # Find records with passed effective_until
        records = frappe.get_all(
            self.doctype,
            filters={
                "status": "active",
                "effective_until": ["<", now]
            },
            fields=["name"]
        )
        
        for r in records:
            frappe.db.set_value(self.doctype, r.name, "status", "expired")
            count += 1
        
        # Find records with expired TTL
        records = frappe.get_all(
            self.doctype,
            filters={
                "status": "active",
                "ttl_days": [">", 0]
            },
            fields=["name", "creation", "ttl_days"]
        )
        
        for r in records:
            expiry_date = r.creation + timedelta(days=r.ttl_days)
            if now > expiry_date:
                frappe.db.set_value(self.doctype, r.name, "status", "expired")
                count += 1
        
        return count
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dict with various statistics about memory storage
        """
        stats = {
            "total_records": frappe.db.count(self.doctype),
            "active_records": frappe.db.count(self.doctype, {"status": "active"}),
            "expired_records": frappe.db.count(self.doctype, {"status": "expired"}),
            "archived_records": frappe.db.count(self.doctype, {"status": "archived"}),
            "superseded_records": frappe.db.count(self.doctype, {"status": "superseded"}),
            "by_scope_type": {},
            "by_memory_type": {},
            "by_index_backend": {},
            "fts_indexed": frappe.db.count(self.doctype, {"fts_indexed": 1}),
            "vector_indexed": frappe.db.count(self.doctype, {"vector_indexed": 1}),
        }
        
        # Count by scope type
        for scope in ScopeType:
            count = frappe.db.count(self.doctype, {"scope_type": scope.value})
            if count > 0:
                stats["by_scope_type"][scope.value] = count
        
        # Count by memory type
        for mem_type in MemoryType:
            count = frappe.db.count(self.doctype, {"memory_type": mem_type.value})
            if count > 0:
                stats["by_memory_type"][mem_type.value] = count
        
        # Count by index backend
        for backend in IndexBackend:
            count = frappe.db.count(self.doctype, {"index_backend": backend.value})
            if count > 0:
                stats["by_index_backend"][backend.value] = count
        
        return stats


def get_storage() -> MemoryStorage:
    """Factory function to get a MemoryStorage instance."""
    return MemoryStorage()
