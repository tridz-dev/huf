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
	def before_validate(self):
		self.set_defaults()

	def validate(self):
		self.validate_chunk_settings()
		self.validate_vector_settings()
		self.validate_pgvector_settings()
		self._warn_if_embedding_changed()
		
	def set_defaults(self):
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

		if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", self.pgvector_table_name or ""):
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

	def _warn_if_embedding_changed(self):
		"""Warn if embedding model/provider changed and chunks already exist."""
		if self.is_new():
			return
		if not self.total_chunks:
			return
		# Check if embedding_model or embedding_provider changed
		old_model = frappe.db.get_value("Knowledge Source", self.name, "embedding_model")
		old_provider = frappe.db.get_value("Knowledge Source", self.name, "embedding_provider")
		if old_model != self.embedding_model or old_provider != self.embedding_provider:
			frappe.msgprint(
				_(
					"Warning: You changed the embedding model or provider, but this Knowledge Source "
					"already has {0} indexed chunks. Existing chunks were embedded with a different "
					"model and will return incorrect search results. "
					"Use 'Rebuild Index' to re-embed all chunks with the new model."
				).format(self.total_chunks),
				title=_("Embedding Provider Changed"),
				indicator="orange",
			)
	
	def before_save(self):
		self.set_defaults()
	
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


@frappe.whitelist()
def test_connection(knowledge_source: str):
	"""Test pgvector connection and embedding config for a Knowledge Source."""
	doc = frappe.get_doc("Knowledge Source", knowledge_source)

	results = {}

	# Test pgvector connection
	if doc.knowledge_type == "pgvector":
		try:
			from huf.ai.knowledge.backends.pgvector_backend import PGVectorBackend
			backend = PGVectorBackend()
			from huf.ai.knowledge.indexer import _build_backend_config
			config = _build_backend_config(doc)
			backend.initialize(knowledge_source, config)
			stats = backend.get_stats()
			results["pgvector"] = {"status": "ok", "chunk_count": stats.get("chunk_count", 0)}
		except Exception as e:
			results["pgvector"] = {"status": "error", "message": str(e)[:300]}

	# Test embedding config
	if doc.embedding_model:
		try:
			from huf.ai.knowledge.embedding import get_embedding, resolve_embedding_config
			config = resolve_embedding_config(knowledge_source)
			embedding = get_embedding(
				"connection test",
				model=config["model"],
				api_key=config.get("api_key"),
				api_base=config.get("api_base"),
			)
			results["embedding"] = {"status": "ok", "dimension": len(embedding)}
		except Exception as e:
			results["embedding"] = {"status": "error", "message": str(e)[:300]}

	all_ok = all(v["status"] == "ok" for v in results.values())
	return {
		"success": all_ok,
		"results": results,
		"message": _("All connections OK") if all_ok else _("One or more connections failed — see details"),
	}
