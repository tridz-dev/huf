# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for Redis Vector backend."""

import unittest
from unittest.mock import Mock, patch, MagicMock


class MockFrappe:
	"""Minimal frappe stand-in for tests that run without a Frappe bench."""

	@staticmethod
	def scrub(name):
		return name.lower().replace(" ", "_")

	@staticmethod
	def logger():
		return Mock()


class MockRedisModule:
	"""Minimal redis module stand-in."""

	def __init__(self):
		self.Redis = MagicMock(return_value=MagicMock())

	def reset(self):
		self.Redis = MagicMock(return_value=MagicMock())


class MockRedisVLModule:
	"""Minimal redisvl module stand-in for IndexSchema construction."""

	def __init__(self):
		self.schema = MagicMock()
		self.schema.IndexSchema.from_dict.return_value = MagicMock()

	def reset(self):
		self.schema = MagicMock()
		self.schema.IndexSchema.from_dict.return_value = MagicMock()


class TestRedisBackend(unittest.TestCase):
	"""Test cases for RedisBackend."""

	@classmethod
	def setUpClass(cls):
		cls.mock_frappe = MockFrappe()
		cls.mock_redis_mod = MockRedisModule()
		cls.mock_redisvl_mod = MockRedisVLModule()
		cls.frappe_patcher = patch.dict("sys.modules", {
			"frappe": cls.mock_frappe,
			"redis": cls.mock_redis_mod,
			"redisvl": cls.mock_redisvl_mod,
			"redisvl.schema": cls.mock_redisvl_mod.schema,
		})
		cls.frappe_patcher.start()
		from huf.ai.knowledge.backends import redis_backend as rb
		cls.rb = rb

	@classmethod
	def tearDownClass(cls):
		cls.frappe_patcher.stop()

	def setUp(self):
		self.mock_redis_mod.reset()
		self.mock_redisvl_mod.reset()
		self.backend = self.rb.RedisBackend()

		self.patcher_config = patch("huf.ai.knowledge.embedding.resolve_embedding_config")
		self.mock_resolve = self.patcher_config.start()
		self.mock_resolve.return_value = {"model": "test-model", "api_key": "test", "api_base": "test"}

		self.patcher_embeds = patch("huf.ai.knowledge.embedding.get_embeddings")
		self.mock_get_embeds = self.patcher_embeds.start()
		self.mock_get_embeds.return_value = [[0.1] * 1536 for _ in range(10)]

		self.patcher_embed = patch("huf.ai.knowledge.embedding.get_embedding")
		self.mock_get_embed = self.patcher_embed.start()
		self.mock_get_embed.return_value = [0.1] * 1536

	def tearDown(self):
		self.patcher_config.stop()
		self.patcher_embeds.stop()
		self.patcher_embed.stop()

	def _make_query(self, **kwargs):
		q = MagicMock()
		for k, v in kwargs.items():
			setattr(q, k, v)
		return q

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_initialize(self, mock_redis_vector_store, mock_storage_context):
		"""Test backend initialization builds a RedisVectorStore from config."""
		mock_vector_store = MagicMock()
		mock_vector_store.index_name = "huf_test_source"
		mock_redis_vector_store.return_value = mock_vector_store

		config = {
			"host": "localhost",
			"port": 6379,
			"vector_dimension": 1536,
			"index_prefix": "test",
		}

		self.backend.initialize("test_source", config)

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.config, config)

		self.mock_redis_mod.Redis.assert_called_once()
		redis_call_kwargs = self.mock_redis_mod.Redis.call_args.kwargs
		self.assertEqual(redis_call_kwargs["host"], "localhost")
		self.assertEqual(redis_call_kwargs["port"], 6379)

		mock_redis_vector_store.assert_called_once()
		vs_call_kwargs = mock_redis_vector_store.call_args.kwargs
		self.assertIn("redis_client", vs_call_kwargs)
		self.assertIn("schema", vs_call_kwargs)

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_add_chunks(self, mock_redis_vector_store, mock_storage_context):
		"""Test adding chunks to the backend."""
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})

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
		self.assertTrue(mock_vector_store.add.called)
		added_documents = mock_vector_store.add.call_args[0][0]
		self.assertEqual(len(added_documents), 2)
		self.assertEqual(added_documents[0].metadata["input_id"], "input_1")

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_add_empty_chunks(self, mock_redis_vector_store, mock_storage_context):
		"""Test adding an empty list of chunks."""
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})

		count = self.backend.add_chunks([])

		self.assertEqual(count, 0)
		mock_vector_store.add.assert_not_called()

	@patch("huf.ai.knowledge.backends.redis_backend.ExactMatchFilter")
	@patch("huf.ai.knowledge.backends.redis_backend.MetadataFilters")
	@patch("huf.ai.knowledge.backends.redis_backend.VectorStoreQuery")
	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_search(
		self,
		mock_redis_vector_store,
		mock_storage_context,
		mock_vector_store_query,
		mock_metadata_filters,
		mock_exact_match_filter,
	):
		"""Test search functionality."""
		mock_vector_store_query.side_effect = self._make_query
		mock_metadata_filters.side_effect = lambda filters: self._make_query(filters=filters)
		mock_exact_match_filter.side_effect = lambda key, value: self._make_query(key=key, value=value)

		mock_vector_store = MagicMock()
		mock_node = MagicMock()
		mock_node.text = "Test result"
		mock_node.metadata = {
			"chunk_id": "chunk_1",
			"source_title": "Test Doc",
			"knowledge_source": "test_source",
		}
		mock_result = MagicMock()
		mock_result.nodes = [mock_node]
		mock_result.similarities = [0.95]
		mock_vector_store.query.return_value = mock_result
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		self.assertEqual(results[0].score, 0.95)
		self.assertTrue(mock_vector_store.query.called)

	@patch("huf.ai.knowledge.backends.redis_backend.ExactMatchFilter")
	@patch("huf.ai.knowledge.backends.redis_backend.MetadataFilters")
	@patch("huf.ai.knowledge.backends.redis_backend.VectorStoreQuery")
	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_delete_chunks(
		self,
		mock_redis_vector_store,
		mock_storage_context,
		mock_vector_store_query,
		mock_metadata_filters,
		mock_exact_match_filter,
	):
		"""Test deleting chunks by input_id."""
		mock_vector_store_query.side_effect = self._make_query
		mock_metadata_filters.side_effect = lambda filters: self._make_query(filters=filters)
		mock_exact_match_filter.side_effect = lambda key, value: self._make_query(key=key, value=value)

		mock_vector_store = MagicMock()
		count_result = MagicMock()
		count_result.nodes = [MagicMock(), MagicMock()]
		mock_vector_store.query.return_value = count_result
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})

		deleted_count = self.backend.delete_chunks("input_to_delete")

		self.assertEqual(deleted_count, 2)
		self.assertTrue(mock_vector_store.delete_nodes.called)

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_clear(self, mock_redis_vector_store, mock_storage_context):
		"""Test clearing all chunks."""
		mock_ft = MagicMock()
		mock_vector_store = MagicMock()
		mock_vector_store.client.ft.return_value = mock_ft
		mock_vector_store.index_name = "huf_test_source"
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})
		self.backend.clear()

		mock_ft.dropindex.assert_called_once_with(delete_documents=True)
		self.assertTrue(mock_redis_vector_store.call_count >= 2)

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_get_stats(self, mock_redis_vector_store, mock_storage_context):
		"""Test getting backend statistics."""
		mock_ft = MagicMock()
		mock_ft.info.return_value = {"num_docs": 5}
		mock_vector_store = MagicMock()
		mock_vector_store.client.ft.return_value = mock_ft
		mock_vector_store.index_name = "huf_test_source"
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})
		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "redis")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["chunk_count"], 5)

	@patch("huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE", True)
	@patch("huf.ai.knowledge.backends.redis_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.redis_backend.RedisVectorStore")
	def test_health_check(self, mock_redis_vector_store, mock_storage_context):
		"""Test health check functionality."""
		mock_vector_store = MagicMock()
		mock_vector_store.client.ping.return_value = True
		mock_redis_vector_store.return_value = mock_vector_store

		self.backend.initialize("test_source", {"vector_dimension": 1536})
		is_healthy, message = self.backend.health_check()

		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")

	def test_health_check_not_initialized(self):
		"""Test health check when not initialized."""
		backend = self.rb.RedisBackend()

		is_healthy, message = backend.health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	def test_supports_filters(self):
		"""Test that backend reports filter support."""
		backend = self.rb.RedisBackend()
		self.assertTrue(backend.supports_filters())

	def test_supports_hybrid_search(self):
		"""Test that backend reports no hybrid search support."""
		backend = self.rb.RedisBackend()
		self.assertFalse(backend.supports_hybrid_search())


class TestRedisBackendUnit(unittest.TestCase):
	"""Unit tests for RedisBackend that don't require dependencies."""

	@classmethod
	def setUpClass(cls):
		cls.mock_frappe = MockFrappe()
		cls.mock_redis_mod = MockRedisModule()
		cls.mock_redisvl_mod = MockRedisVLModule()
		cls.frappe_patcher = patch.dict("sys.modules", {
			"frappe": cls.mock_frappe,
			"redis": cls.mock_redis_mod,
			"redisvl": cls.mock_redisvl_mod,
			"redisvl.schema": cls.mock_redisvl_mod.schema,
		})
		cls.frappe_patcher.start()
		from huf.ai.knowledge.backends import redis_backend as rb
		cls.rb = rb

	@classmethod
	def tearDownClass(cls):
		cls.frappe_patcher.stop()

	def test_class_structure(self):
		"""Test that RedisBackend has all required methods."""
		required_methods = [
			"initialize",
			"add_chunks",
			"delete_chunks",
			"search",
			"clear",
			"get_stats",
			"health_check",
			"supports_filters",
			"supports_hybrid_search",
		]

		for method in required_methods:
			self.assertTrue(
				hasattr(self.rb.RedisBackend, method),
				f"RedisBackend missing method: {method}"
			)

	def test_initialize_without_dependencies(self):
		"""Test that initialization fails gracefully when dependencies are missing."""
		with patch.object(self.rb, "LLAMAINDEX_AVAILABLE", False):
			backend = self.rb.RedisBackend()
			with self.assertRaises(ImportError):
				backend.initialize("test_source", {})


if __name__ == "__main__":
	unittest.main()
