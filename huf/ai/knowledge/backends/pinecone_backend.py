# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Pinecone serverless backend using the LlamaIndex adapter."""

import os
import re
from typing import Any

import frappe
from frappe import _

from . import ChunkResult, KnowledgeBackend
from .llamaindex_base import LLAMAINDEX_AVAILABLE, LlamaIndexBackend

try:
	from llama_index.vector_stores.pinecone import PineconeVectorStore
	from pinecone import Pinecone, ServerlessSpec

	PINECONE_DEPS_AVAILABLE = True
except ImportError:
	PINECONE_DEPS_AVAILABLE = False


# Pinecone index names: lowercase alphanumerics and hyphens, 1-45 chars,
# starting and ending with an alphanumeric.
VALID_INDEX_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,43}[a-z0-9])?$")

# Clouds supported by Pinecone's ServerlessSpec.
PINECONE_CLOUDS = ("aws", "gcp", "azure")

# Upper bound for the metadata-filter count query run before delete_chunks;
# Pinecone caps query top_k at 10000 on serverless indexes.
COUNT_QUERY_LIMIT = 10000


def _stat_get(obj: Any, key: str, default: Any = 0) -> Any:
	"""Read a stat key from a Pinecone response object (attribute or dict-style)."""
	if isinstance(obj, dict):
		return obj.get(key, default)
	return getattr(obj, key, default)


class PineconeBackend(LlamaIndexBackend, KnowledgeBackend):
	"""Pinecone (cloud-only, serverless) backend for HUF knowledge storage.

	This mirrors the PGVector backend pattern: HUF resolves and generates
	embeddings, while LlamaIndex owns the vector-store adapter behavior.

	Isolation: a single Pinecone index can be shared by many sites and
	knowledge sources — each source is pinned to its own namespace (default:
	scrubbed ``<site>_<source>``), and ``site_name`` / ``knowledge_source``
	metadata filters are applied on top of the namespace as a second guard.
	"""

	_backend_type = "pinecone"

	def __init__(self):
		super().__init__()
		self.api_key = None
		self.index_name = None
		self.namespace = None
		self.dimension = 1536
		self.cloud = "aws"
		self.region = "us-east-1"
		self._client = None

	@classmethod
	def get_advanced_config_schema(cls) -> list[dict[str, Any]]:
		return [
			{
				"key": "pinecone_api_key",
				"label": "Pinecone API Key",
				"type": "text",
				"default": "",
				"help_text": (
					"Pinecone API key from app.pinecone.io. Values in Advanced Config are "
					"stored as plaintext — prefer the PINECONE_API_KEY environment "
					"variable on shared systems."
				),
			},
			{
				"key": "pinecone_index_name",
				"label": "Pinecone Index Name",
				"type": "text",
				"default": "",
				"help_text": (
					"Pinecone serverless index name: lowercase letters, numbers, and "
					"hyphens only (max 45 characters). Created automatically with this "
					"source's vector dimension and cosine metric if it does not exist."
				),
			},
			{
				"key": "pinecone_namespace",
				"label": "Pinecone Namespace",
				"type": "text",
				"default": "",
				"help_text": (
					"Namespace isolating this knowledge source's vectors inside the "
					"shared index. Defaults to a per-site, per-source namespace; keep "
					"it stable after indexing."
				),
			},
			{
				"key": "pinecone_cloud",
				"label": "Pinecone Cloud",
				"type": "select",
				"default": "aws",
				"options": ["aws", "gcp", "azure"],
				"help_text": (
					"Cloud provider for the serverless index. Only applies when the index is first created."
				),
			},
			{
				"key": "pinecone_region",
				"label": "Pinecone Region",
				"type": "text",
				"default": "us-east-1",
				"help_text": (
					"Cloud region for the serverless index (e.g. us-east-1, eu-west-1). "
					"Only applies when the index is first created."
				),
			},
		]

	def _check_dependencies(self) -> None:
		if not LLAMAINDEX_AVAILABLE or not PINECONE_DEPS_AVAILABLE:
			frappe.throw(
				_(
					"llama-index-vector-stores-pinecone is required for pinecone knowledge sources. "
					"Install it with: pip install llama-index-vector-stores-pinecone"
				)
			)

	def _validate_config(self) -> None:
		self.api_key = self.config.get("pinecone_api_key") or os.environ.get("PINECONE_API_KEY")
		if not self.api_key:
			frappe.throw(
				_(
					"Pinecone API key is required. Set pinecone_api_key in Advanced Config "
					"or the PINECONE_API_KEY environment variable."
				)
			)

		self.index_name = self.config.get("pinecone_index_name")
		if not self.index_name or not VALID_INDEX_NAME.match(self.index_name):
			frappe.throw(
				_(
					"Pinecone index name must be 1-45 characters of lowercase letters, "
					"numbers, and hyphens, starting and ending with a letter or number."
				)
			)

		self.namespace = self.config.get("pinecone_namespace") or self._default_namespace()

		self.dimension = int(self.config.get("vector_dimension") or 1536)
		if self.dimension <= 0:
			frappe.throw(_("Pinecone vector dimension must be positive"))

		self.cloud = (self.config.get("pinecone_cloud") or "aws").lower()
		if self.cloud not in PINECONE_CLOUDS:
			frappe.throw(_("Pinecone cloud must be one of: {0}").format(", ".join(PINECONE_CLOUDS)))
		self.region = self.config.get("pinecone_region") or "us-east-1"

	def _default_namespace(self) -> str:
		"""Per-site, per-source namespace used when none is configured."""
		return f"{frappe.scrub(frappe.local.site)}_{frappe.scrub(self.knowledge_source)}"

	def _create_vector_store(self) -> Any:
		self._client = Pinecone(api_key=self.api_key)
		self._ensure_index()
		return PineconeVectorStore(
			pinecone_index=self._client.Index(self.index_name),
			namespace=self.namespace,
		)

	def _ensure_index(self) -> None:
		"""Create the serverless index if missing; validate dimension if present."""
		if not self._client.has_index(self.index_name):
			self._client.create_index(
				name=self.index_name,
				dimension=self.dimension,
				metric="cosine",
				spec=ServerlessSpec(cloud=self.cloud, region=self.region),
			)
			return

		existing_dimension = int(_stat_get(self._client.describe_index(self.index_name), "dimension", 0))
		if existing_dimension and existing_dimension != self.dimension:
			frappe.throw(
				_(
					"Pinecone index '{0}' has dimension {1}, but this Knowledge Source is "
					"configured for dimension {2}. Point the source at another index (or "
					"recreate the index) so the dimensions match."
				).format(self.index_name, existing_dimension, self.dimension)
			)

	def _build_chunk_metadata(self, chunk: dict[str, Any], chunk_id: str) -> dict[str, Any]:
		return {
			"site_name": frappe.local.site,
			"knowledge_source": self.knowledge_source,
			"input_id": chunk["input_id"],
			"input_type": chunk["input_type"],
			"chunk_id": chunk_id,
			"source_title": chunk.get("source_title"),
			"chunk_index": chunk.get("chunk_index"),
			"char_start": chunk.get("char_start"),
			"char_end": chunk.get("char_end"),
			**(chunk.get("metadata") or {}),
		}

	def _build_search_filters(self, filters: dict[str, Any] | None) -> Any:
		from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters

		llama_filters = [
			ExactMatchFilter(key="site_name", value=frappe.local.site),
			ExactMatchFilter(key="knowledge_source", value=self.knowledge_source),
		]
		if filters:
			llama_filters.extend(ExactMatchFilter(key=key, value=value) for key, value in filters.items())
		return MetadataFilters(filters=llama_filters)

	def delete_chunks(self, input_id: str) -> int:
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters

		filters = MetadataFilters(
			filters=[
				ExactMatchFilter(key="site_name", value=frappe.local.site),
				ExactMatchFilter(key="knowledge_source", value=self.knowledge_source),
				ExactMatchFilter(key="input_id", value=input_id),
			]
		)
		try:
			# Pinecone deletes do not report a count, so count the matching
			# vectors first via a metadata-filter query.
			chunk_count = len(self.vector_store.get_nodes(filters=filters, limit=COUNT_QUERY_LIMIT))
			if not chunk_count:
				return 0
			self.vector_store.delete_nodes(filters=filters)
			return chunk_count
		except Exception as exc:
			frappe.logger().warning(f"Pinecone delete_chunks error for {input_id}: {exc!s}")
			return 0

	def clear(self) -> None:
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		try:
			# The adapter's clear() deletes every vector in this namespace only.
			self.vector_store.clear()
		except Exception as exc:
			frappe.logger().warning(f"Pinecone clear error for {self.knowledge_source}: {exc!s}")
			raise

	def get_stats(self) -> dict[str, Any]:
		stats = {
			"backend_type": "pinecone",
			"knowledge_source": self.knowledge_source,
			"index_name": self.index_name,
			"namespace": self.namespace,
			"initialized": self._initialized,
			"vector_dimension": self.dimension,
			"chunk_count": 0,
			"index_vector_count": 0,
			"size_bytes": 0,
		}

		if self._initialized and self.vector_store:
			try:
				index_stats = self.vector_store.client.describe_index_stats()
				stats["index_vector_count"] = int(_stat_get(index_stats, "total_vector_count", 0) or 0)
				namespace_stats = _stat_get(index_stats, "namespaces", None) or {}
				if self.namespace in namespace_stats:
					stats["chunk_count"] = int(_stat_get(namespace_stats[self.namespace], "vector_count", 0) or 0)
			except Exception as exc:
				frappe.logger().warning(f"Pinecone get_stats error for {self.knowledge_source}: {exc!s}")

		return stats
