"""
HUF Memory System - SQLite FTS5 Backend

Full-text search backend using SQLite FTS5 virtual tables.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import frappe
from frappe.utils import get_site_path

from ..index_backend import IndexResult, MemoryIndexBackend, ScopeFilter, SearchResult

if TYPE_CHECKING:
    from ..storage_service import MemoryRecord


class SQLiteFTSBackend(MemoryIndexBackend):
    """
    Full-text search backend using SQLite FTS5 virtual tables.
    
    This backend provides keyword and phrase search over memory records
    using Porter stemming and unicode61 tokenization.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        super().__init__("sqlite_fts")
        self.db_path = db_path or self._get_default_db_path()
        self.table_name = "memory_fts_idx"
        self._conn: Optional[sqlite3.Connection] = None
    
    def _get_default_db_path(self) -> str:
        """Get the default SQLite database path."""
        site_path = get_site_path()
        return f"{site_path}/memory_fts.db"
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Enable FTS5
            self._conn.enable_load_extension(True)
            try:
                self._conn.load_extension("fts5")
            except sqlite3.OperationalError:
                # FTS5 might be built-in
                pass
        return self._conn
    
    async def initialize(self) -> bool:
        """Initialize the FTS5 virtual table."""
        try:
            conn = self._get_connection()
            
            # Create FTS5 virtual table (contentless design)
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING fts5(
                    record_id UNINDEXED,
                    title,
                    summary_text,
                    data_json,
                    tags,
                    scope_type UNINDEXED,
                    scope_key UNINDEXED,
                    memory_type UNINDEXED,
                    agent UNINDEXED,
                    tokenize='porter unicode61'
                )
            """)
            
            # Create auxiliary tables for efficient metadata queries
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name}_meta (
                    record_id TEXT PRIMARY KEY,
                    scope_type TEXT,
                    scope_key TEXT,
                    memory_type TEXT,
                    agent TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            self._initialized = True
            return True
            
        except Exception as e:
            frappe.log_error(f"FTS backend initialization failed: {str(e)}")
            return False
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        """Index a memory record to FTS5."""
        try:
            conn = self._get_connection()
            
            # Serialize data_json for text search
            data_json_text = json.dumps(record.data_json, ensure_ascii=False) if record.data_json else ""
            tags_text = ",".join(record.tags) if record.tags else ""
            
            # Insert into FTS table
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.table_name} (
                    record_id, title, summary_text, data_json, tags,
                    scope_type, scope_key, memory_type, agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.name,
                record.title or "",
                record.summary_text or "",
                data_json_text,
                tags_text,
                record.scope_type.value if record.scope_type else "",
                record.scope_key or "",
                record.memory_type.value if record.memory_type else "",
                record.agent or ""
            ))
            
            # Update metadata table
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.table_name}_meta (
                    record_id, scope_type, scope_key, memory_type, agent, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.name,
                record.scope_type.value if record.scope_type else None,
                record.scope_key,
                record.memory_type.value if record.memory_type else None,
                record.agent,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            
            return IndexResult(
                success=True,
                record_id=record.name,
                backend=self.backend_name,
                indexed_at=datetime.now()
            )
            
        except Exception as e:
            frappe.log_error(f"FTS index failed for {record.name}: {str(e)}")
            return IndexResult(
                success=False,
                record_id=record.name,
                backend=self.backend_name,
                indexed_at=datetime.now(),
                error_message=str(e)
            )
    
    async def search(
        self,
        query: str,
        scope: ScopeFilter,
        limit: int = 10
    ) -> list[SearchResult]:
        """Search using FTS5 match syntax."""
        try:
            conn = self._get_connection()
            
            # Build scope filter conditions
            conditions = []
            params = []
            
            if scope.scope_type:
                conditions.append("m.scope_type = ?")
                params.append(scope.scope_type)
            
            if scope.scope_key:
                conditions.append("m.scope_key = ?")
                params.append(scope.scope_key)
            
            if scope.agent:
                conditions.append("m.agent = ?")
                params.append(scope.agent)
            
            if scope.memory_type:
                conditions.append("m.memory_type = ?")
                params.append(scope.memory_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Execute FTS query with snippet generation
            cursor = conn.execute(f"""
                SELECT 
                    f.record_id,
                    f.title,
                    f.summary_text,
                    f.tags,
                    rank AS score,
                    snippet({self.table_name}, 2, '<mark>', '</mark>', '...', 32) AS snippet
                FROM {self.table_name} f
                JOIN {self.table_name}_meta m ON f.record_id = m.record_id
                WHERE {self.table_name} MATCH ? AND {where_clause}
                ORDER BY rank
                LIMIT ?
            """, (query, *params, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    record_id=row["record_id"],
                    score=row["score"],
                    backend=self.backend_name,
                    matched_fields=self._extract_matched_fields(row),
                    snippet=row["snippet"]
                ))
            
            return results
            
        except Exception as e:
            frappe.log_error(f"FTS search failed for query '{query}': {str(e)}")
            return []
    
    def _extract_matched_fields(self, row: sqlite3.Row) -> list[str]:
        """Determine which fields matched based on content."""
        fields = []
        # This is a simplified version - in practice, you'd use FTS5 aux functions
        # to determine which columns matched
        if row["title"]:
            fields.append("title")
        if row["summary_text"]:
            fields.append("summary_text")
        if row["tags"]:
            fields.append("tags")
        return fields
    
    async def delete(self, record_id: str) -> bool:
        """Remove a record from the FTS index."""
        try:
            conn = self._get_connection()
            
            conn.execute(
                f"DELETE FROM {self.table_name} WHERE record_id = ?",
                (record_id,)
            )
            conn.execute(
                f"DELETE FROM {self.table_name}_meta WHERE record_id = ?",
                (record_id,)
            )
            conn.commit()
            
            return True
            
        except Exception as e:
            frappe.log_error(f"FTS delete failed for {record_id}: {str(e)}")
            return False
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """Reindex a record (delete then insert)."""
        await self.delete(record.name)
        return await self.index(record)
    
    async def clear(self) -> bool:
        """Clear all records from the FTS index."""
        try:
            conn = self._get_connection()
            conn.execute(f"DELETE FROM {self.table_name}")
            conn.execute(f"DELETE FROM {self.table_name}_meta")
            conn.commit()
            return True
        except Exception as e:
            frappe.log_error(f"FTS clear failed: {str(e)}")
            return False
    
    async def count(self) -> int:
        """Get the number of indexed records."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            return cursor.fetchone()[0]
        except Exception:
            return 0
    
    def is_available(self) -> bool:
        """Check if FTS5 is available."""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')")
            result = cursor.fetchone()[0]
            return result == 1 or self._initialized
        except Exception:
            return False
