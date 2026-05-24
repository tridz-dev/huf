# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for Redis Vector backend."""

import unittest
from unittest.mock import Mock, patch, MagicMock

# Skip tests if llama-index not installed
try:
	from llama_index.vector_stores.redis import RedisVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-redis not installed")
class TestRedisBackend(unittest.TestCase):
	"""Test cases for RedisBackend."""
	
	def setUp(self):
		"""Set up test fixtures."""
		self.mock_frappe = Mock()
		self.mock_frappe.scrub = lambda x: x.lower().replace(" ", "_")
		self.mock_frappe.logger = Mock(return_value=Mock())
		
		self.patcher = patch.dict('sys.modules', {'frappe': self.mock_frappe})
		self.patcher.start()
		
		# Import after patching
		from huf.ai.knowledge.backends.redis_backend import RedisBackend
		self.backend_class = RedisBackend
		self.backend = RedisBackend()
	
	def tearDown(self):
		"""Clean up after tests."""
		self.patcher.stop()
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	def test_initialize(self, mock_storage_context, mock_redis_vector_store):
		"""Test backend initialization."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		
		# Test initialization
		config = {
			"host": "localhost",
			"port": 6379,
			"vector_dimension": 1536,
			"index_prefix": "test"
		}
		
		self.backend.initialize("test_source", config)
		
		# Verify
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.config, config)
		self.assertTrue(self.backend._initialized)
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	@patch('huf.ai.knowledge.backends.redis_backend.VectorStoreIndex')
	def test_add_chunks(self, mock_vector_store_index, mock_storage_context, mock_redis_vector_store):
		"""Test adding chunks."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		mock_index = MagicMock()
		mock_vector_store_index.from_documents.return_value = mock_index
		
		# Initialize backend
		config = {"host": "localhost", "port": 6379}
		self.backend.initialize("test_source", config)
		
		# Test adding chunks
		chunks = [
			{
				"text": "Test content 1",
				"input_id": "input_1",
				"input_type": "document",
				"chunk_id": "chunk_1",
				"source_title": "Test Doc"
			},
			{
				"text": "Test content 2",
				"input_id": "input_2",
				"input_type": "document",
				"chunk_id": "chunk_2",
				"source_title": "Test Doc 2"
			}
		]
		
		count = self.backend.add_chunks(chunks)
		
		# Verify
		self.assertEqual(count, 2)
		mock_vector_store_index.from_documents.assert_called_once()
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	@patch('huf.ai.knowledge.backends.redis_backend.VectorStoreIndex')
	def test_search(self, mock_vector_store_index, mock_storage_context, mock_redis_vector_store):
		"""Test search functionality."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		
		mock_index = MagicMock()
		mock_vector_store_index.from_vector_store.return_value = mock_index
		
		mock_retriever = MagicMock()
		mock_index.as_retriever.return_value = mock_retriever
		
		# Create mock node result
		mock_node = MagicMock()
		mock_node.text = "Test result"
		mock_node.metadata = {
			"chunk_id": "chunk_1",
			"source_title": "Test Doc",
			"knowledge_source": "test_source"
		}
		mock_node.score = 0.95
		mock_retriever.retrieve.return_value = [mock_node]
		
		# Initialize backend
		config = {"host": "localhost", "port": 6379}
		self.backend.initialize("test_source", config)
		self.backend.index = mock_index
		
		# Test search
		results = self.backend.search("test query", top_k=5)
		
		# Verify
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		self.assertEqual(results[0].score, 0.95)
		mock_retriever.retrieve.assert_called_once_with("test query")
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	def test_get_stats(self, mock_storage_context, mock_redis_vector_store):
		"""Test getting stats."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		
		# Initialize backend
		config = {
			"host": "redis.example.com",
			"port": 6380,
			"index_prefix": "test_prefix"
		}
		self.backend.initialize("test_source", config)
		
		# Test get_stats
		stats = self.backend.get_stats()
		
		# Verify
		self.assertEqual(stats["backend_type"], "redis")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertEqual(stats["host"], "redis.example.com")
		self.assertEqual(stats["port"], 6380)
		self.assertTrue(stats["initialized"])
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	def test_health_check_success(self, mock_storage_context, mock_redis_vector_store):
		"""Test health check with success."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_client = MagicMock()
		mock_redis_client.ping.return_value = True
		mock_vector_store._redis_client = mock_redis_client
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		
		# Initialize backend
		config = {"host": "localhost", "port": 6379}
		self.backend.initialize("test_source", config)
		
		# Test health check
		healthy, message = self.backend.health_check()
		
		# Verify
		self.assertTrue(healthy)
		self.assertIn("Healthy", message)
		mock_redis_client.ping.assert_called_once()
	
	@patch('huf.ai.knowledge.backends.redis_backend.RedisVectorStore')
	@patch('huf.ai.knowledge.backends.redis_backend.StorageContext')
	def test_health_check_failure(self, mock_storage_context, mock_redis_vector_store):
		"""Test health check with failure."""
		# Setup mocks
		mock_vector_store = MagicMock()
		mock_redis_client = MagicMock()
		mock_redis_client.ping.side_effect = Exception("Connection refused")
		mock_vector_store._redis_client = mock_redis_client
		mock_redis_vector_store.return_value = mock_vector_store
		mock_storage_context.from_defaults.return_value = MagicMock()
		
		# Initialize backend
		config = {"host": "localhost", "port": 6379}
		self.backend.initialize("test_source", config)
		
		# Test health check
		healthy, message = self.backend.health_check()
		
		# Verify
		self.assertFalse(healthy)
		self.assertIn("failed", message)
	
	def test_supports_filters(self):
		"""Test supports_filters returns True."""
		self.assertTrue(self.backend.supports_filters())
	
	def test_supports_hybrid_search(self):
		"""Test supports_hybrid_search returns False."""
		self.assertFalse(self.backend.supports_hybrid_search())
	
	def test_add_chunks_empty(self):
		"""Test adding empty chunks list."""
		count = self.backend.add_chunks([])
		self.assertEqual(count, 0)


class TestRedisBackendWithoutLlamaIndex(unittest.TestCase):
	"""Test cases when llama-index is not available."""
	
	@patch('huf.ai.knowledge.backends.redis_backend.LLAMAINDEX_AVAILABLE', False)
	def test_initialize_without_llamaindex(self):
		"""Test initialization fails when llama-index not installed."""
		with patch.dict('sys.modules', {'frappe': Mock()}):
			from huf.ai.knowledge.backends.redis_backend import RedisBackend
			backend = RedisBackend()
			
			with self.assertRaises(ImportError) as context:
				backend.initialize("test", {})
			
			self.assertIn("llama-index-vector-stores-redis", str(context.exception))


if __name__ == "__main__":
	unittest.main()
