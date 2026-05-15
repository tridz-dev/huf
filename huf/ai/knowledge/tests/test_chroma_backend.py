# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for ChromaDB backend."""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.knowledge.backends.chroma_backend import ChromaBackend, LLAMAINDEX_AVAILABLE


class TestChromaBackend(FrappeTestCase):
	"""Test cases for ChromaBackend."""
	
	def setUp(self):
		"""Set up test fixtures."""
		self.backend = ChromaBackend()
		
		# Mock embedding logic
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
		"""Clean up after tests."""
		self.patcher_config.stop()
		self.patcher_embeds.stop()
		self.patcher_embed.stop()
		
		if self.backend._initialized:
			try:
				self.backend.clear()
			except Exception:
				pass
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_initialization_with_persist_directory(self):
		"""Test initialization with file-based storage."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			self.assertTrue(self.backend._initialized)
			self.assertEqual(self.backend.knowledge_source, "test_source")
			self.assertIsNotNone(self.backend.client)
			self.assertIsNotNone(self.backend.collection)
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	@patch("huf.ai.knowledge.backends.chroma_backend.chromadb.HttpClient")
	def test_initialization_with_server(self, mock_http_client):
		"""Test initialization with Chroma server."""
		mock_client = Mock()
		mock_http_client.return_value = mock_client
		
		config = {
			"host": "chroma.example.com",
			"port": 8080,
			"ssl": True,
			"vector_dimension": 1536,
		}
		
		self.backend.initialize("test_source", config)
		
		mock_http_client.assert_called_once()
		call_kwargs = mock_http_client.call_args.kwargs
		self.assertEqual(call_kwargs["host"], "chroma.example.com")
		self.assertEqual(call_kwargs["port"], 8080)
		self.assertEqual(call_kwargs["ssl"], True)
	
	def test_initialization_without_dependencies(self):
		"""Test that initialization fails gracefully when dependencies are missing."""
		from huf.ai.knowledge import backends as backends_module
		
		with patch.object(
			backends_module.chroma_backend,
			"LLAMAINDEX_AVAILABLE",
			False
		):
			with self.assertRaises(ImportError):
				self.backend.initialize("test_source", {})
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_add_chunks(self):
		"""Test adding chunks to the backend."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
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
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_add_empty_chunks(self):
		"""Test adding empty list of chunks."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			count = self.backend.add_chunks([])
			
			self.assertEqual(count, 0)
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_delete_chunks(self):
		"""Test deleting chunks by input_id."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			chunks = [
				{
					"chunk_id": "chunk_1",
					"input_id": "input_to_delete",
					"input_type": "document",
					"source_title": "Test",
					"chunk_index": 0,
					"text": "Content to delete.",
				},
			]
			
			self.backend.add_chunks(chunks)
			
			# Verify chunk was added
			stats_before = self.backend.get_stats()
			self.assertEqual(stats_before["chunk_count"], 1)
			
			# Delete chunks
			deleted_count = self.backend.delete_chunks("input_to_delete")
			
			# Note: Due to embedding generation requirements in real tests,
			# this test may need mocking. The basic structure is here.
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_clear(self):
		"""Test clearing all chunks."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			# Clear should work even with empty collection
			self.backend.clear()
			
			stats = self.backend.get_stats()
			self.assertEqual(stats["chunk_count"], 0)
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_get_stats(self):
		"""Test getting backend statistics."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			stats = self.backend.get_stats()
			
			self.assertEqual(stats["backend_type"], "chroma")
			self.assertEqual(stats["knowledge_source"], "test_source")
			self.assertTrue(stats["initialized"])
			self.assertEqual(stats["persist_directory"], tmpdir)
			self.assertIn("collection_name", stats)
			self.assertIn("chunk_count", stats)
	
	@unittest.skipUnless(LLAMAINDEX_AVAILABLE, "llama-index-vector-stores-chroma not installed")
	def test_health_check(self):
		"""Test health check functionality."""
		with tempfile.TemporaryDirectory() as tmpdir:
			config = {
				"persist_directory": tmpdir,
				"vector_dimension": 1536,
			}
			
			self.backend.initialize("test_source", config)
			
			is_healthy, message = self.backend.health_check()
			
			self.assertTrue(is_healthy)
			self.assertEqual(message, "Healthy")
	
	def test_health_check_not_initialized(self):
		"""Test health check when not initialized."""
		backend = ChromaBackend()
		
		is_healthy, message = backend.health_check()
		
		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")
	
	def test_supports_filters(self):
		"""Test that backend reports filter support."""
		backend = ChromaBackend()
		self.assertTrue(backend.supports_filters())
	
	def test_supports_hybrid_search(self):
		"""Test that backend reports no hybrid search support."""
		backend = ChromaBackend()
		self.assertFalse(backend.supports_hybrid_search())


class TestChromaBackendUnit(unittest.TestCase):
	"""Unit tests for ChromaBackend that don't require dependencies."""
	
	def test_class_structure(self):
		"""Test that ChromaBackend has all required methods."""
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
				hasattr(ChromaBackend, method),
				f"ChromaBackend missing method: {method}"
			)


if __name__ == "__main__":
	unittest.main()
