# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document
from frappe import _


VECTOR_KNOWLEDGE_TYPES = {"sqlite_vec", "chroma", "pgvector"}
PGVECTOR_DISTANCE_METRICS = {"cosine", "l2", "inner_product"}
PGVECTOR_INDEX_TYPES = {"none", "hnsw", "ivfflat"}
PGVECTOR_SSLMODES = {"prefer", "require", "disable", "allow", "verify-ca", "verify-full"}


class KnowledgeSource(Document):
	def validate(self):
		self.validate_chunk_settings()
		self.validate_vector_settings()
		self.validate_pgvector_settings()
		
	def validate_chunk_settings(self):
		if self.chunk_size and self.chunk_size < 100:
			frappe.throw(_("Chunk size must be at least 100 characters"))
		if self.chunk_overlap and self.chunk_overlap >= self.chunk_size:
			frappe.throw(_("Chunk overlap must be less than chunk size"))

	def validate_vector_settings(self):
		if self.knowledge_type in VECTOR_KNOWLEDGE_TYPES:
			if not self.embedding_model:
				frappe.throw(_("Embedding Model is required for vector knowledge types"))
			if not self.vector_dimension or self.vector_dimension <= 0:
				frappe.throw(_("Vector Dimension must be a positive integer for vector knowledge types"))

		if self.knowledge_type == "sqlite_vec":
			from huf.ai.knowledge.backends.sqlite_vec_backend import check_sqlite_vec_available

			if not check_sqlite_vec_available():
				frappe.throw(
					_("sqlite_vec requires loadable SQLite extensions. "
					  "Install pysqlite3-binary: pip install pysqlite3-binary. "
					  "Or use sqlite_fts for keyword search.")
				)

	def validate_pgvector_settings(self):
		if self.knowledge_type != "pgvector":
			return

		if not self.pgvector_connection_mode:
			self.pgvector_connection_mode = "External PostgreSQL"
		if not self.pgvector_table_name:
			self.pgvector_table_name = "huf_knowledge_vectors"
		if not self.pgvector_distance_metric:
			self.pgvector_distance_metric = "cosine"
		if not self.pgvector_index_type:
			self.pgvector_index_type = "hnsw"
		if not self.pgvector_sslmode:
			self.pgvector_sslmode = "prefer"

		if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", self.pgvector_table_name):
			frappe.throw(_("PGVector Table Name must be a valid PostgreSQL identifier"))

		if self.pgvector_distance_metric not in PGVECTOR_DISTANCE_METRICS:
			frappe.throw(_("Invalid PGVector Distance Metric"))

		if self.pgvector_index_type not in PGVECTOR_INDEX_TYPES:
			frappe.throw(_("Invalid PGVector Index Type"))

		if self.pgvector_sslmode not in PGVECTOR_SSLMODES:
			frappe.throw(_("Invalid PGVector SSL Mode"))

		if self.pgvector_connection_mode == "External PostgreSQL":
			missing_fields = []
			for fieldname, label in {
				"pgvector_host": "Host",
				"pgvector_port": "Port",
				"pgvector_database": "Database",
				"pgvector_user": "User",
			}.items():
				if not self.get(fieldname):
					missing_fields.append(label)

			if missing_fields:
				frappe.throw(
					_("Missing PGVector connection fields: {0}").format(", ".join(missing_fields))
				)

			if int(self.pgvector_port or 0) <= 0:
				frappe.throw(_("PGVector Port must be a positive integer"))

		elif self.pgvector_connection_mode == "Site PostgreSQL":
			if frappe.conf.db_type != "postgres":
				frappe.throw(
					_("Site PostgreSQL mode requires the Frappe site database to be PostgreSQL. "
					  "Use External PostgreSQL for MariaDB-backed sites.")
				)
		else:
			frappe.throw(_("Invalid PGVector Connection Mode"))
	
	def before_save(self):
		if not self.chunk_size:
			self.chunk_size = 512
		if not self.chunk_overlap:
			self.chunk_overlap = 50
		if not self.status:
			self.status = "Pending"
		if self.knowledge_type == "pgvector":
			if not self.pgvector_connection_mode:
				self.pgvector_connection_mode = "External PostgreSQL"
			if not self.pgvector_table_name:
				self.pgvector_table_name = "huf_knowledge_vectors"
			if not self.pgvector_distance_metric:
				self.pgvector_distance_metric = "cosine"
			if not self.pgvector_index_type:
				self.pgvector_index_type = "hnsw"
			if not self.pgvector_sslmode:
				self.pgvector_sslmode = "prefer"
	
	def on_trash(self):
		# Delete SQLite artifact file
		if self.sqlite_file:
			try:
				file_doc = frappe.get_doc("File", {"file_url": self.sqlite_file})
				file_doc.delete(ignore_permissions=True)
			except Exception:
				pass
		
		# Delete all related inputs
		frappe.db.delete("Knowledge Input", {"knowledge_source": self.name})


@frappe.whitelist()
def rebuild_index(knowledge_source: str):
	"""Trigger a full index rebuild for the knowledge source."""
	from huf.ai.knowledge.indexer import rebuild_knowledge_index
	
	doc = frappe.get_doc("Knowledge Source", knowledge_source)
	doc.status = "Rebuilding"
	doc.save()
	
	frappe.enqueue(
		rebuild_knowledge_index,
		queue="long",
		knowledge_source=knowledge_source,
		job_id=f"rebuild_index_{knowledge_source}",
		deduplicate=True,
	)
	
	return {"status": "queued", "message": _("Index rebuild has been queued")}


@frappe.whitelist()
def test_search(knowledge_source: str, query: str, top_k: int = 5):
	"""Test search against a knowledge source."""
	from huf.ai.knowledge.retriever import knowledge_search
	
	results = knowledge_search(
		query=query,
		knowledge_source=knowledge_source,
		top_k=int(top_k)
	)
	
	return results
