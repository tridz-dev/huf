"""LlamaIndex-compatible VectorStore adapter for sqlite-vec."""

import json
import sqlite3
from typing import Any, Dict, List, Optional

try:
	from llama_index.core.schema import BaseNode, TextNode
	from llama_index.core.vector_stores.types import (
		BasePydanticVectorStore,
		VectorStoreQuery,
		VectorStoreQueryResult,
	)
	from pydantic import ConfigDict

	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


def _check_llamaindex():
	if not LLAMAINDEX_AVAILABLE:
		raise ImportError(
			"llama-index-core is required for the LlamaIndex VectorStore adapter. "
			"Install it with: pip install llama-index-core"
		)


if LLAMAINDEX_AVAILABLE:

	class SQLiteVecVectorStore(BasePydanticVectorStore):
		"""LlamaIndex VectorStore backed by sqlite-vec."""

		model_config = ConfigDict(arbitrary_types_allowed=True)

		db_path: str
		dimension: int = 1536
		table_name: str = "nodes_vec"
		nodes_table: str = "nodes"

		_conn: Any = None

		def __init__(self, **kwargs):
			super().__init__(**kwargs)
			self._init_db()

		def _init_db(self):
			self._conn = sqlite3.connect(self.db_path)
			self._conn.row_factory = sqlite3.Row
			import sqlite_vec  # type: ignore

			sqlite_vec.load(self._conn)
			self._conn.execute(
				f"""
				CREATE TABLE IF NOT EXISTS {self.nodes_table} (
					node_id TEXT PRIMARY KEY,
					text TEXT,
					ref_doc_id TEXT,
					metadata_json TEXT
				)
				"""
			)
			self._conn.execute(
				f"""
				CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING vec0(
					embedding FLOAT[{self.dimension}]
				)
				"""
			)
			self._conn.commit()

		@property
		def client(self) -> Any:
			return self._conn

		def add(self, nodes: List[BaseNode], **kwargs: Any) -> List[str]:
			ids: List[str] = []
			for node in nodes:
				node_id = node.node_id
				embedding = node.get_embedding()
				metadata = node.metadata or {}

				existing_row = self._conn.execute(
					f"SELECT rowid FROM {self.nodes_table} WHERE node_id = ?",
					(node_id,),
				).fetchone()
				if existing_row:
					self._conn.execute(f"DELETE FROM {self.table_name} WHERE rowid = ?", (existing_row[0],))

				self._conn.execute(
					f"INSERT OR REPLACE INTO {self.nodes_table}(node_id, text, ref_doc_id, metadata_json) VALUES (?, ?, ?, ?)",
					(node_id, node.get_content(), node.ref_doc_id or "", json.dumps(metadata)),
				)
				rowid = self._conn.execute(
					f"SELECT rowid FROM {self.nodes_table} WHERE node_id = ?",
					(node_id,),
				).fetchone()[0]
				self._conn.execute(
					f"INSERT INTO {self.table_name}(rowid, embedding) VALUES (?, ?)",
					(rowid, json.dumps(embedding)),
				)
				ids.append(node_id)

			self._conn.commit()
			return ids

		def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
			rows = self._conn.execute(
				f"SELECT rowid FROM {self.nodes_table} WHERE ref_doc_id = ?", (ref_doc_id,)
			).fetchall()
			for row in rows:
				self._conn.execute(f"DELETE FROM {self.table_name} WHERE rowid = ?", (row["rowid"],))
			self._conn.execute(f"DELETE FROM {self.nodes_table} WHERE ref_doc_id = ?", (ref_doc_id,))
			self._conn.commit()

		def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
			if query.query_embedding is None:
				return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

			top_k = query.similarity_top_k or 5
			rows = self._conn.execute(
				f"""
				SELECT n.node_id, n.text, n.metadata_json, v.distance
				FROM {self.table_name} v
				JOIN {self.nodes_table} n ON n.rowid = v.rowid
				WHERE v.embedding MATCH ? AND k = ?
				ORDER BY v.distance ASC
				""",
				(json.dumps(query.query_embedding), top_k),
			).fetchall()

			nodes: List[BaseNode] = []
			similarities: List[float] = []
			ids: List[str] = []
			for row in rows:
				metadata: Dict[str, Any] = {}
				if row["metadata_json"]:
					metadata = json.loads(row["metadata_json"])
				nodes.append(TextNode(id_=row["node_id"], text=row["text"] or "", metadata=metadata))
				similarities.append(1.0 / (1.0 + float(row["distance"] or 0.0)))
				ids.append(row["node_id"])

			return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

		def get_nodes(
			self,
			node_ids: Optional[List[str]] = None,
			filters: Optional[Any] = None,
		) -> List[BaseNode]:
			if not node_ids:
				return []

			placeholders = ",".join(["?" for _ in node_ids])
			rows = self._conn.execute(
				f"SELECT node_id, text, metadata_json FROM {self.nodes_table} WHERE node_id IN ({placeholders})",
				node_ids,
			).fetchall()

			result_nodes = []
			for row in rows:
				metadata = json.loads(row["metadata_json"] or "{}")
				result_nodes.append(TextNode(id_=row["node_id"], text=row["text"] or "", metadata=metadata))

			return result_nodes