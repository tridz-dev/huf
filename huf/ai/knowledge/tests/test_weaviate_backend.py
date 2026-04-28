# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for Weaviate knowledge backend."""

import unittest
from unittest.mock import Mock, patch, MagicMock

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.knowledge.backends.weaviate_backend import WeaviateBackend, LLAMAINDEX_AVAILABLE


class TestWeaviateBackend(FrappeTestCase):
	"""Test cases for WeaviateBackend."""
	
	def setUp(self):
		"""Set up test fixtures."""
		self.backend = WeaviateBackend()
		self.config = {
			"host": "localhost",
			"port": 8080,
			"vector_dimension": 1536,
		}
		
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	def test_initialize_self_hosted(self, mock_storage_context, mock_vector_store):
		"""Test initialization with self-hosted Weaviate."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.from_params.return_value = mock_vector_store_instance
		mock_storage_context_instance = MagicMock()
		mock_storage_context.from_defaults.return_value = mock_storage_context_instance
		
		# Initialize
		self.backend.initialize("test_source", self.config)
		
		# Assertions
		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		mock_vector_store.assert_called_once()
		mock_storage_context.from_defaults.assert_called_once()
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	def test_initialize_cloud(self, mock_storage_context, mock_vector_store):
		"""Test initialization with Weaviate Cloud."""
		config = {
			"weaviate_cloud_url": "https://test-cluster.weaviate.cloud",
			"api_key": "test-api-key",
			"vector_dimension": 1536,
		}
		
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.from_params.return_value = mock_vector_store_instance
		
		# Initialize
		self.backend.initialize("test_cloud_source", config)
		
		# Check that cloud URL and API key were used
		call_kwargs = mock_vector_store.call_args.kwargs
		self.assertEqual(call_kwargs.get("url"), "https://test-cluster.weaviate.cloud")
		self.assertEqual(call_kwargs.get("api_key"), "test-api-key")
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	def test_class_name_sanitization(self):
		"""Test that class names are properly sanitized for Weaviate."""
		# Test various source names
		test_cases = [
			("my_source", "Huf_my_source"),
			("My Source", "Huf_my_source"),
			("123-source", "Class_123_source"),
			("special!@#chars", "Huf_special___chars"),
		]
		
		for source_name, expected_pattern in test_cases:
			backend = WeaviateBackend()
			backend.knowledge_source = source_name
			class_name = backend.get_class_name()
			
			# Class name should start with uppercase letter
			self.assertTrue(class_name[0].isupper())
			# Should only contain alphanumeric and underscore
			self.assertTrue(all(c.isalnum() or c == "_" for c in class_name))
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.weaviate_backend.VectorStoreIndex")
	def test_add_chunks(self, mock_index_class, mock_storage_context, mock_vector_store):
		"""Test adding chunks to Weaviate."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.return_value = mock_vector_store_instance
		mock_storage_context_instance = MagicMock()
		mock_storage_context.from_defaults.return_value = mock_storage_context_instance
		mock_index = MagicMock()
		mock_index_class.from_documents.return_value = mock_index
		
		# Initialize and add chunks
		self.backend.initialize("test_source", self.config)
		
		chunks = [
			{
				"text": "Test chunk 1",
				"input_id": "input_1",
				"input_type": "text",
				"chunk_id": "chunk_1",
				"source_title": "Test Source",
			}
		]
		
		count = self.backend.add_chunks(chunks)
		
		# Should return number of chunks added
		self.assertEqual(count, 1)
		mock_index_class.from_documents.assert_called_once()
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	@patch("huf.ai.knowledge.backends.weaviate_backend.VectorStoreIndex")
	def test_search(self, mock_index_class, mock_storage_context, mock_vector_store):
		"""Test searching Weaviate."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.return_value = mock_vector_store_instance
		mock_storage_context_instance = MagicMock()
		mock_storage_context.from_defaults.return_value = mock_storage_context_instance
		
		# Mock index and retriever
		mock_index = MagicMock()
		mock_retriever = MagicMock()
		mock_index.as_retriever.return_value = mock_retriever
		mock_index_class.from_vector_store.return_value = mock_index
		
		# Mock search results
		mock_node = MagicMock()
		mock_node.text = "Test result"
		mock_node.metadata = {
			"chunk_id": "chunk_1",
			"source_title": "Test Source",
			"knowledge_source": "test_source",
		}
		mock_node.score = 0.95
		mock_retriever.retrieve.return_value = [mock_node]
		
		# Initialize and search
		self.backend.initialize("test_source", self.config)
		self.backend.index = mock_index
		
		results = self.backend.search("test query", top_k=5)
		
		# Should return results
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].chunk_id, "chunk_1")
		self.assertEqual(results[0].text, "Test result")
		self.assertEqual(results[0].score, 0.95)
	
	def test_empty_chunks(self):
		"""Test adding empty chunks list."""
		# Should return 0 without error
		count = self.backend.add_chunks([])
		self.assertEqual(count, 0)
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	def test_health_check(self, mock_storage_context, mock_vector_store):
		"""Test health check."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.return_value = mock_vector_store_instance
		mock_client = MagicMock()
		mock_vector_store_instance._client = mock_client
		
		# Initialize
		self.backend.initialize("test_source", self.config)
		
		# Health check should pass
		is_healthy, message = self.backend.health_check()
		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")
		mock_client.get_meta.assert_called_once()
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	def test_health_check_failure(self, mock_storage_context, mock_vector_store):
		"""Test health check with failure."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.return_value = mock_vector_store_instance
		mock_client = MagicMock()
		mock_client.get_meta.side_effect = Exception("Connection failed")
		mock_vector_store_instance._client = mock_client
		
		# Initialize
		self.backend.initialize("test_source", self.config)
		
		# Health check should fail
		is_healthy, message = self.backend.health_check()
		self.assertFalse(is_healthy)
		self.assertIn("Connection failed", message)
	
	def test_supports_filters(self):
		"""Test that Weaviate supports filters."""
		self.assertTrue(self.backend.supports_filters())
	
	def test_supports_hybrid_search(self):
		"""Test that Weaviate supports hybrid search."""
		self.assertTrue(self.backend.supports_hybrid_search())
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-weaviate not installed")
	@patch("huf.ai.knowledge.backends.weaviate_backend.WeaviateVectorStore")
	@patch("huf.ai.knowledge.backends.weaviate_backend.StorageContext")
	def test_get_stats(self, mock_storage_context, mock_vector_store):
		"""Test getting backend statistics."""
		# Setup mocks
		mock_vector_store_instance = MagicMock()
		mock_vector_store.return_value = mock_vector_store_instance
		mock_collection = MagicMock()
		mock_vector_store_instance._collection = mock_collection
		mock_aggregate = MagicMock()
		mock_aggregate.total_count = 42
		mock_collection.aggregate.over_all.return_value = mock_aggregate
		
		# Initialize
		self.backend.initialize("test_source", self.config)
		
		# Get stats
		stats = self.backend.get_stats()
		
		self.assertEqual(stats["backend_type"], "weaviate")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["object_count"], 42)


class TestWeaviateBackendImport(unittest.TestCase):
	"""Test import handling when llama-index is not available."""
	
	@patch("huf.ai.knowledge.backends.weaviate_backend.LLAMAINDEX_AVAILABLE", False)
	def test_initialize_without_llamaindex(self):
		"""Test that initialization raises ImportError when llama-index is not available."""
		backend = WeaviateBackend()
		with self.assertRaises(ImportError) as context:
			backend.initialize("test", {})
		
		self.assertIn("llama-index-vector-stores-weaviate", str(context.exception))


if __name__ == "__main__":
	frappe.connect(site="test_site")
	unittest.main()
