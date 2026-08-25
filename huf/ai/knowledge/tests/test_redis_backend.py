# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the Redis knowledge backend and its hook registration.

The backend talks to RediSearch through redisvl directly. Unit tests mock the
redis client and redisvl SearchIndex (no live Redis server required); the
schema, filter-expression, and query construction use real redisvl objects.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends import redis_backend as rb
from huf.ai.knowledge.backends.redis_backend import RedisBackend


class TestRedisBackend(unittest.TestCase):
	"""Mocked unit tests for RedisBackend (no live Redis server required)."""

	def setUp(self):
		self.backend = RedisBackend()

		self._previous_site = getattr(frappe.local, "site", None)
		frappe.local.site = "test_site"
		# frappe.throw/msgprint and logging need these bound outside a site context,
		# and restored because bench run-tests runs inside a real frappe process
		# whose frappe.local.flags carries state the rest of the suite depends on.
		self._previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()
		self._previous_message_log = getattr(frappe.local, "message_log", None)
		frappe.local.message_log = []

		self.patcher_config = patch("huf.ai.knowledge.embedding.resolve_embedding_config")
		self.mock_resolve = self.patcher_config.start()
		self.mock_resolve.return_value = {"model": "test-model", "api_key": "test", "api_base": "test"}

		self.patcher_embeds = patch("huf.ai.knowledge.embedding.get_embeddings")
		self.mock_get_embeds = self.patcher_embeds.start()
		self.mock_get_embeds.side_effect = lambda texts, **_: [[0.1] * 1536 for _ in texts]

		self.patcher_embed = patch("huf.ai.knowledge.embedding.get_embedding")
		self.mock_get_embed = self.patcher_embed.start()
		self.mock_get_embed.return_value = [0.1] * 1536

		# Outside a site context frappe.logger() tries to open site log files.
		self.patcher_logger = patch.object(frappe, "logger", MagicMock())
		self.patcher_logger.start()

	def tearDown(self):
		self.patcher_config.stop()
		self.patcher_embeds.stop()
		self.patcher_embed.stop()
		self.patcher_logger.stop()

		if self._previous_site is None:
			if hasattr(frappe.local, "site"):
				del frappe.local.site
		else:
			frappe.local.site = self._previous_site

		if self._previous_flags is None:
			if hasattr(frappe.local, "flags"):
				del frappe.local.flags
		else:
			frappe.local.flags = self._previous_flags

		if self._previous_message_log is None:
			if hasattr(frappe.local, "message_log"):
				del frappe.local.message_log
		else:
			frappe.local.message_log = self._previous_message_log

	def _initialize(self, config=None):
		"""Initialize the backend with the redis client and SearchIndex mocked."""
		config = config or {"vector_dimension": 1536}

		self.mock_redis_module = MagicMock()
		self.mock_redis_client = MagicMock()
		self.mock_redis_module.Redis.return_value = self.mock_redis_client
		self.mock_index = MagicMock()
		self.mock_index_cls = MagicMock(return_value=self.mock_index)

		patchers = [
			patch.object(rb, "REDIS_DEPS_AVAILABLE", True),
			patch.object(rb, "redis", self.mock_redis_module, create=True),
			patch.object(rb, "SearchIndex", self.mock_index_cls, create=True),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.backend.initialize("test_source", config)

	def test_initialize(self):
		"""Initialization builds a Redis client, IndexSchema, and SearchIndex."""
		self._initialize(
			{
				"redis_host": "localhost",
				"redis_port": 6379,
				"vector_dimension": 1536,
				"redis_index_prefix": "test",
			}
		)

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.index_name, "test_test_source")

		self.mock_redis_module.Redis.assert_called_once_with(host="localhost", port=6379)

		schema = self.mock_index_cls.call_args[0][0]
		schema_dict = schema.to_dict()
		self.assertEqual(schema_dict["index"]["name"], "test_test_source")
		vector_field = next(f for f in schema_dict["fields"] if f["type"] == "vector")
		self.assertEqual(vector_field["attrs"]["dims"], 1536)
		tag_names = {f["name"] for f in schema_dict["fields"] if f["type"] == "tag"}
		self.assertIn("site_name", tag_names)
		self.assertIn("knowledge_source", tag_names)
		self.assertIn("input_id", tag_names)

		self.assertIs(self.mock_index_cls.call_args[0][1], self.mock_redis_client)
		self.mock_index.create.assert_called_once_with(overwrite=False)

	def test_initialize_existing_index_is_ok(self):
		"""An 'index already exists' error from create() is tolerated."""
		config = {"vector_dimension": 1536}

		self.mock_redis_module = MagicMock()
		self.mock_index = MagicMock()
		self.mock_index.create.side_effect = Exception("Index already exists")
		mock_index_cls = MagicMock(return_value=self.mock_index)

		with (
			patch.object(rb, "REDIS_DEPS_AVAILABLE", True),
			patch.object(rb, "redis", self.mock_redis_module, create=True),
			patch.object(rb, "SearchIndex", mock_index_cls, create=True),
		):
			self.backend.initialize("test_source", config)

		self.assertTrue(self.backend._initialized)

	def test_initialize_credentials_only_when_set(self):
		"""Username/password are passed to redis.Redis only when configured."""
		self._initialize({"redis_username": "acl_user", "redis_password": "secret"})

		call_kwargs = self.mock_redis_module.Redis.call_args.kwargs
		self.assertEqual(call_kwargs["username"], "acl_user")
		self.assertEqual(call_kwargs["password"], "secret")

	def test_initialize_defaults(self):
		"""Missing config falls back to localhost:6379 and the huf prefix."""
		self._initialize({})

		call_kwargs = self.mock_redis_module.Redis.call_args.kwargs
		self.assertEqual(call_kwargs["host"], "localhost")
		self.assertEqual(call_kwargs["port"], 6379)
		self.assertNotIn("username", call_kwargs)
		self.assertNotIn("password", call_kwargs)
		self.assertEqual(self.backend.index_name, "huf_test_source")

	def test_initialize_without_dependencies(self):
		"""Initialization fails with a clear error when redisvl is missing."""
		with patch.object(rb, "REDIS_DEPS_AVAILABLE", False):
			with self.assertRaises(frappe.ValidationError):
				self.backend.initialize("test_source", {})

	def test_initialize_invalid_prefix(self):
		"""An invalid index prefix is rejected during validation."""
		self.backend.config = {"redis_index_prefix": "bad prefix!"}
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_add_chunks(self):
		"""Chunks are embedded by HUF and loaded with scoping metadata."""
		self._initialize()

		chunks = [
			{
				"chunk_id": "chunk_1",
				"input_id": "input_1",
				"input_type": "document",
				"source_title": "Test Document",
				"chunk_index": 0,
				"text": "This is test content for chunk 1.",
				"metadata": {"key": "value"},
			},
			{
				"chunk_id": "chunk_2",
				"input_id": "input_1",
				"input_type": "document",
				"source_title": "Test Document",
				"chunk_index": 1,
				"text": "This is test content for chunk 2.",
				"metadata": {"key": "value2"},
			},
		]

		count = self.backend.add_chunks(chunks)

		self.assertEqual(count, 2)
		self.mock_index.load.assert_called_once()
		records = self.mock_index.load.call_args[0][0]
		self.assertEqual(len(records), 2)
		self.assertEqual(records[0]["id"], "chunk_1")
		self.assertEqual(records[0]["input_id"], "input_1")
		self.assertEqual(records[0]["knowledge_source"], "test_source")
		self.assertEqual(records[0]["site_name"], "test_site")
		self.assertEqual(records[0]["key"], "value")
		# Vectors are stored as float32 bytes: 1536 dims * 4 bytes.
		self.assertIsInstance(records[0]["vector"], bytes)
		self.assertEqual(len(records[0]["vector"]), 1536 * 4)

	def test_add_empty_chunks(self):
		"""Adding an empty chunk list is a no-op."""
		self._initialize()

		count = self.backend.add_chunks([])

		self.assertEqual(count, 0)
		self.mock_index.load.assert_not_called()

	def test_search(self):
		"""Search embeds the query via HUF and scopes by site/knowledge_source."""
		self._initialize()

		self.mock_index.query.return_value = [
			{
				"id": "huf_test_source/vector_chunk_1",
				"vector_distance": "0.05",
				"text": "Test result",
				"chunk_id": "chunk_1",
				"source_title": "Test Doc",
				"knowledge_source": "test_source",
				"site_name": "test_site",
				"input_id": "input_1",
				"input_type": "document",
			}
		]

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		self.assertAlmostEqual(results[0].score, 0.95)
		self.assertEqual(results[0].chunk_id, "chunk_1")
		self.assertEqual(results[0].title, "Test Doc")
		self.assertEqual(results[0].source, "test_source")
		# Scoping keys are stripped from the returned metadata.
		self.assertNotIn("site_name", results[0].metadata)
		self.assertNotIn("knowledge_source", results[0].metadata)
		self.assertEqual(results[0].metadata["input_id"], "input_1")

		query_arg = self.mock_index.query.call_args[0][0]
		self.assertEqual(query_arg._num_results, 5)
		filter_str = str(query_arg._filter_expression)
		self.assertIn("site_name", filter_str)
		self.assertIn("test_site", filter_str)
		self.assertIn("knowledge_source", filter_str)
		self.assertIn("test_source", filter_str)

	def test_search_with_caller_filters(self):
		"""Caller-supplied filters are ANDed onto the scoping expression."""
		self._initialize()
		self.mock_index.query.return_value = []

		self.backend.search("test query", filters={"input_type": "document"})

		filter_str = str(self.mock_index.query.call_args[0][0]._filter_expression)
		self.assertIn("input_type", filter_str)
		self.assertIn("document", filter_str)

	def test_search_empty_query(self):
		"""An empty query short-circuits without touching the index."""
		self._initialize()

		self.assertEqual(self.backend.search(""), [])
		self.assertEqual(self.backend.search("   "), [])
		self.mock_index.query.assert_not_called()

	def test_delete_chunks(self):
		"""Deletion uses a raw RediSearch tag query plus client.delete."""
		self._initialize()

		mock_ft = MagicMock()
		search_result = MagicMock()
		search_result.docs = [MagicMock(id="doc:1"), MagicMock(id="doc:2")]
		mock_ft.search.return_value = search_result
		self.mock_redis_client.ft.return_value = mock_ft

		deleted_count = self.backend.delete_chunks("input_to_delete")

		self.assertEqual(deleted_count, 2)
		mock_ft.search.assert_called_once()
		self.assertEqual(self.mock_redis_client.delete.call_count, 2)
		self.mock_redis_client.delete.assert_any_call("doc:1")
		self.mock_redis_client.delete.assert_any_call("doc:2")
		# Regression guard: the old test asserted on delete_nodes, which no
		# implementation path calls. Deletion goes through ft().search + delete.
		self.mock_index.query.assert_not_called()

	def test_delete_chunks_escapes_tag_query(self):
		"""Non-alphanumeric characters in the input_id are escaped for the tag query."""
		self.assertEqual(rb._escape_tag("KI-0001/abc"), "KI\\-0001\\/abc")

	def test_clear(self):
		"""Clear drops the index (with documents) and recreates it."""
		self._initialize()

		self.backend.clear()

		self.mock_index.delete.assert_called_once_with(drop=True)
		# Index is recreated so it exists for subsequent operations.
		self.assertEqual(self.mock_index_cls.call_count, 2)

	def test_get_stats(self):
		"""Stats report backend metadata and num_docs from ft().info()."""
		self._initialize()

		mock_ft = MagicMock()
		mock_ft.info.return_value = {"num_docs": 5}
		self.mock_redis_client.ft.return_value = mock_ft

		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "redis")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertEqual(stats["index_name"], "huf_test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["chunk_count"], 5)

	def test_health_check(self):
		"""Health check pings Redis and verifies the index exists."""
		self._initialize()
		self.mock_redis_client.ping.return_value = True
		self.mock_index.exists.return_value = True

		is_healthy, message = self.backend.health_check()

		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")

	def test_health_check_not_initialized(self):
		"""Health check reports unhealthy before initialization."""
		is_healthy, message = RedisBackend().health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	def test_supports_flags(self):
		"""Redis supports metadata filters but not hybrid search."""
		backend = RedisBackend()
		self.assertTrue(backend.supports_filters())
		self.assertFalse(backend.supports_hybrid_search())

	def test_advanced_config_schema(self):
		"""The advanced-config schema exposes the Redis connection settings."""
		schema = RedisBackend.get_advanced_config_schema()
		keys = {entry["key"] for entry in schema}

		self.assertEqual(
			keys,
			{"redis_host", "redis_port", "redis_username", "redis_password", "redis_index_prefix"},
		)
		for entry in schema:
			self.assertIn("label", entry)
			self.assertIn("type", entry)
			self.assertIn("default", entry)
			self.assertIn("help_text", entry)

		port_entry = next(e for e in schema if e["key"] == "redis_port")
		self.assertEqual(port_entry["type"], "number")
		self.assertEqual(port_entry["min"], 1)
		self.assertEqual(port_entry["max"], 65535)

		password_entry = next(e for e in schema if e["key"] == "redis_password")
		self.assertIn("plain text", password_entry["help_text"])


class TestRedisBackendRegistry(unittest.TestCase):
	"""Redis resolves through the hook-based backend registry."""

	def _clear_registry_cache(self):
		if hasattr(frappe.local, "huf_backend_registry"):
			del frappe.local.huf_backend_registry

	def setUp(self):
		self._clear_registry_cache()
		# frappe.get_attr consults local.flags outside install/uninstall,
		# and restored because bench run-tests runs inside a real frappe process.
		self._previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()

	def tearDown(self):
		if self._previous_flags is None:
			if hasattr(frappe.local, "flags"):
				del frappe.local.flags
		else:
			frappe.local.flags = self._previous_flags

		self._clear_registry_cache()

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_redis_resolves_via_huf_hook(self, mock_get_hooks, mock_get_installed_apps):
		from huf.ai.knowledge.backends import KnowledgeBackend, _discover_backends, get_backend

		mock_get_installed_apps.return_value = ["huf"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "huf":
				return [{"redis": "huf.ai.knowledge.backends.redis_backend.RedisBackend"}]
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()
		self.assertEqual(registry["redis"], "huf.ai.knowledge.backends.redis_backend.RedisBackend")

		backend_class = get_backend("redis")
		self.assertIs(backend_class, RedisBackend)
		self.assertTrue(issubclass(backend_class, KnowledgeBackend))
		self.assertEqual(backend_class._backend_type, "redis")

	def test_redis_not_in_builtin_backends(self):
		"""Redis is hook-registered, not a built-in backend."""
		from huf.ai.knowledge.backends import _BUILTIN_BACKENDS

		self.assertNotIn("redis", _BUILTIN_BACKENDS)


if __name__ == "__main__":
	unittest.main()
