# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for Pinecone backend."""

import os
import unittest
from unittest.mock import MagicMock, patch, Mock

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.knowledge.backends.pinecone_backend import PineconeBackend, _sanitize_index_name
from huf.ai.backends.factory import BackendFactory


class TestSanitizeIndexName(unittest.TestCase):
	"""Test index name sanitization."""
	
	def test_lowercase_conversion(self):
		"""Test conversion to lowercase."""
		self.assertEqual(_sanitize_index_name("MyIndex"), "myindex")
	
	def test_special_chars_replaced(self):
		"""Test special characters replaced with hyphens."""
		self.assertEqual(_sanitize_index_name("my_index@test"), "my-index-test")
	
	def test_leading_trailing_hyphens_removed(self):
		"""Test leading/trailing hyphens removed."""
		self.assertEqual(_sanitize_index_name("-my-index-"), "my-index")
	
	def test_length_limit(self):
		"""Test name limited to 45 characters."""
		long_name = "a" * 100
		result = _sanitize_index_name(long_name)
		self.assertLessEqual(len(result), 45)
	
	def test_empty_name_fallback(self):
		"""Test fallback for empty names."""
		self.assertEqual(_sanitize_index_name("---"), "huf-knowledge")
		self.assertEqual(_sanitize_index_name(""), "huf-knowledge")
		self.assertEqual(_sanitize_index_name("@#$%"), "huf-knowledge")


class TestPineconeBackend(FrappeTestCase):
	"""Test Pinecone backend implementation."""
	
	def setUp(self):
		"""Set up test fixtures."""
		self.backend = PineconeBackend()
		self.config = {
			"api_key": "test-api-key",
			"index_name": "test-index",
			"namespace": "test-namespace",
			"vector_dimension": 1536,
		}
	
	@patch.dict(os.environ, {"PINECONE_API_KEY": "env-api-key"})
	def test_api_key_from_environment(self):
		"""Test API key can be loaded from environment."""
		backend = PineconeBackend()
		config = {"index_name": "test-index"}
		
		with patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore') as mock_vs:
			mock_vs.return_value = MagicMock()
			backend.initialize("test-source", config)
			
			# Check that api_key from env was passed
			call_kwargs = mock_vs.call_args.kwargs
			self.assertEqual(call_kwargs['api_key'], "env-api-key")
	
	def test_api_key_from_config(self):
		"""Test API key from config takes precedence."""
		with patch.dict(os.environ, {}, clear=True):
			with patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore') as mock_vs:
				mock_vs.return_value = MagicMock()
				self.backend.initialize("test-source", self.config)
				
				call_kwargs = mock_vs.call_args.kwargs
				self.assertEqual(call_kwargs['api_key'], "test-api-key")
	
	def test_missing_api_key_raises_error(self):
		"""Test error raised when API key is missing."""
		with patch.dict(os.environ, {}, clear=True):
			config = {}  # No api_key
			with self.assertRaises(ValueError) as ctx:
				self.backend.initialize("test-source", config)
			self.assertIn("API key required", str(ctx.exception))
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_initialize_sets_properties(self, mock_vs):
		"""Test initialize sets backend properties correctly."""
		mock_vs.return_value = MagicMock()
		
		self.backend.initialize("My Knowledge Source", self.config)
		
		self.assertEqual(self.backend.knowledge_source, "My Knowledge Source")
		self.assertEqual(self.backend._index_name, "test-index")
		self.assertEqual(self.backend._namespace, "test-namespace")
		self.assertTrue(self.backend._initialized)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_index_name_sanitization(self, mock_vs):
		"""Test index name is sanitized from knowledge source."""
		mock_vs.return_value = MagicMock()
		
		config = {"api_key": "test-key"}  # No explicit index_name
		self.backend.initialize("My Test_Source!", config)
		
		call_kwargs = mock_vs.call_args.kwargs
		self.assertEqual(call_kwargs['index_name'], "my-test-source")
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_add_chunks_empty_list(self, mock_vs):
		"""Test add_chunks with empty list returns 0."""
		mock_vs.return_value = MagicMock()
		
		self.backend.initialize("test", self.config)
		result = self.backend.add_chunks([])
		self.assertEqual(result, 0)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.VectorStoreIndex')
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_add_chunks_creates_documents(self, mock_vs, mock_index):
		"""Test add_chunks creates LlamaIndex documents."""
		mock_vs.return_value = MagicMock()
		mock_index.from_documents.return_value = MagicMock()
		
		self.backend.initialize("test", self.config)
		
		chunks = [
			{
				"text": "Test content 1",
				"input_id": "doc1",
				"input_type": "document",
				"chunk_id": "chunk1",
				"source_title": "Test Doc",
			}
		]
		
		result = self.backend.add_chunks(chunks)
		
		self.assertEqual(result, 1)
		mock_index.from_documents.assert_called_once()
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.VectorStoreIndex')
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_search_returns_results(self, mock_vs, mock_index):
		"""Test search returns ChunkResult objects."""
		# Setup mocks
		mock_vs.return_value = MagicMock()
		
		mock_node = MagicMock()
		mock_node.text = "Test result"
		mock_node.metadata = {
			"chunk_id": "chunk1",
			"source_title": "Test Doc",
			"knowledge_source": "test",
		}
		mock_node.score = 0.95
		
		mock_retriever = MagicMock()
		mock_retriever.retrieve.return_value = [mock_node]
		
		mock_index_instance = MagicMock()
		mock_index_instance.as_retriever.return_value = mock_retriever
		mock_index.from_vector_store.return_value = mock_index_instance
		
		self.backend.initialize("test", self.config)
		self.backend.index = mock_index_instance
		
		results = self.backend.search("test query", top_k=5)
		
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].chunk_id, "chunk1")
		self.assertEqual(results[0].text, "Test result")
		self.assertEqual(results[0].score, 0.95)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_health_check_healthy(self, mock_vs):
		"""Test health check returns healthy status."""
		mock_store = MagicMock()
		mock_store._pinecone_index.describe_index_stats.return_value = MagicMock()
		mock_vs.return_value = mock_store
		
		self.backend.initialize("test", self.config)
		is_healthy, message = self.backend.health_check()
		
		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_health_check_uninitialized(self, mock_vs):
		"""Test health check when not initialized."""
		is_healthy, message = self.backend.health_check()
		
		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_health_check_error(self, mock_vs):
		"""Test health check when connection fails."""
		mock_store = MagicMock()
		mock_store._pinecone_index.describe_index_stats.side_effect = Exception("Connection failed")
		mock_vs.return_value = mock_store
		
		self.backend.initialize("test", self.config)
		is_healthy, message = self.backend.health_check()
		
		self.assertFalse(is_healthy)
		self.assertIn("Connection failed", message)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_get_stats(self, mock_vs):
		"""Test get_stats returns expected structure."""
		mock_store = MagicMock()
		mock_stats = MagicMock()
		mock_stats.total_vector_count = 100
		mock_stats.dimension = 1536
		mock_stats.namespaces = {"test-namespace": MagicMock(vector_count=50)}
		mock_store._pinecone_index.describe_index_stats.return_value = mock_stats
		mock_vs.return_value = mock_store
		
		self.backend.initialize("test", self.config)
		stats = self.backend.get_stats()
		
		self.assertEqual(stats["backend_type"], "pinecone")
		self.assertEqual(stats["knowledge_source"], "test")
		self.assertEqual(stats["index_name"], "test-index")
		self.assertEqual(stats["namespace"], "test-namespace")
		self.assertEqual(stats["vector_count"], 100)
		self.assertEqual(stats["namespace_count"], 50)
		self.assertEqual(stats["dimension"], 1536)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_clear_deletes_all(self, mock_vs):
		"""Test clear deletes all vectors in namespace."""
		mock_store = MagicMock()
		mock_vs.return_value = mock_store
		
		self.backend.initialize("test", self.config)
		self.backend.clear()
		
		mock_store._pinecone_index.delete.assert_called_once_with(
			delete_all=True,
			namespace="test-namespace"
		)
	
	@patch('huf.ai.knowledge.backends.pinecone_backend.PineconeVectorStore')
	def test_delete_chunks_by_input_id(self, mock_vs):
		"""Test delete_chunks by input_id."""
		mock_store = MagicMock()
		mock_vs.return_value = mock_store
		
		self.backend.initialize("test", self.config)
		result = self.backend.delete_chunks("doc123")
		
		mock_store._pinecone_index.delete.assert_called_once_with(
			filter={"input_id": {"$eq": "doc123"}},
			namespace="test-namespace"
		)
	
	def test_supports_filters(self):
		"""Test supports_filters returns True."""
		self.assertTrue(self.backend.supports_filters())
	
	def test_supports_hybrid_search(self):
		"""Test supports_hybrid_search returns True."""
		self.assertTrue(self.backend.supports_hybrid_search())


class TestBackendFactory(unittest.TestCase):
	"""Test BackendFactory registration."""
	
	def test_pinecone_registered(self):
		"""Test pinecone backend is registered."""
		self.assertTrue(BackendFactory.is_registered("pinecone"))
	
	def test_create_pinecone_backend(self):
		"""Test creating pinecone backend instance."""
		backend = BackendFactory.create("pinecone")
		self.assertIsInstance(backend, PineconeBackend)


if __name__ == "__main__":
	frappe.init(site="test_site")
	frappe.connect()
	unittest.main()
