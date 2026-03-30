# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for FAISS backend."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Mock frappe before importing backend
frappe_mock = MagicMock()
frappe_mock.get_site_path.return_value = tempfile.mkdtemp()
frappe_mock.scrub = lambda x: x.replace(" ", "_").lower()
frappe_mock.logger.return_value = MagicMock()
frappe_mock.conf.db_name = "test_db"
frappe_mock.conf.db_user = "test_user"
frappe_mock.conf.db_password = "test_password"

import sys
sys.modules["frappe"] = frappe_mock

# Mock llama_index imports
llama_index_mock = MagicMock()
sys.modules["llama_index"] = llama_index_mock
sys.modules["llama_index.core"] = llama_index_mock
sys.modules["llama_index.vector_stores"] = llama_index_mock
sys.modules["llama_index.vector_stores.faiss"] = llama_index_mock

from ..backends.faiss_backend import FAISSBackend
from ..backends.factory import BackendFactory


class TestFAISSBackend(unittest.TestCase):
    """Test cases for FAISSBackend."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.index_path = os.path.join(self.temp_dir, "test.faiss")
        self.config = {
            "index_path": self.index_path,
            "vector_dimension": 384,  # Small dimension for testing
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove test index file if it exists
        if os.path.exists(self.index_path):
            os.remove(self.index_path)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    def test_backend_registration(self):
        """Test that FAISS backend is registered."""
        backends = BackendFactory.list_backends()
        self.assertIn("faiss", backends)
        self.assertEqual(backends["faiss"], FAISSBackend)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    def test_backend_factory_create(self):
        """Test creating backend via factory."""
        backend = BackendFactory.create("faiss")
        self.assertIsInstance(backend, FAISSBackend)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", False)
    def test_initialization_without_llamaindex(self):
        """Test that initialization fails without llama-index."""
        backend = FAISSBackend()
        with self.assertRaises(ImportError) as context:
            backend.initialize("test_source", self.config)
        self.assertIn("llama-index-vector-stores-faiss", str(context.exception))
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    def test_initialization_creates_new_index(self, mock_faiss_store_class):
        """Test that initialization creates a new index when none exists."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        mock_faiss_store_class.from_persist_path = MagicMock()
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        self.assertTrue(backend._initialized)
        self.assertEqual(backend.knowledge_source, "test_source")
        self.assertEqual(backend._dimension, 384)
        self.assertEqual(backend._index_path, self.index_path)
        mock_faiss_store_class.assert_called_once()
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("huf.ai.knowledge.backends.faiss_backend.VectorStoreIndex")
    @patch("os.path.exists")
    def test_initialization_loads_existing_index(
        self, mock_exists, mock_index_class, mock_faiss_store_class
    ):
        """Test that initialization loads existing index if available."""
        mock_exists.return_value = True
        mock_store = MagicMock()
        mock_faiss_store_class.from_persist_path.return_value = mock_store
        mock_index = MagicMock()
        mock_index_class.from_vector_store.return_value = mock_index
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        mock_faiss_store_class.from_persist_path.assert_called_once_with(
            persist_path=self.index_path
        )
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("huf.ai.knowledge.backends.faiss_backend.VectorStoreIndex")
    def test_add_chunks(self, mock_index_class, mock_faiss_store_class):
        """Test adding chunks to the index."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        mock_index = MagicMock()
        mock_index_class.from_documents.return_value = mock_index
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        chunks = [
            {
                "text": "Test chunk 1",
                "input_id": "doc_1",
                "input_type": "document",
                "chunk_id": "chunk_1",
                "source_title": "Test Document",
            },
            {
                "text": "Test chunk 2",
                "input_id": "doc_1",
                "input_type": "document",
                "chunk_id": "chunk_2",
                "source_title": "Test Document",
            },
        ]
        
        count = backend.add_chunks(chunks)
        self.assertEqual(count, 2)
        mock_index_class.from_documents.assert_called_once()
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("huf.ai.knowledge.backends.faiss_backend.VectorStoreIndex")
    def test_add_empty_chunks(self, mock_index_class, mock_faiss_store_class):
        """Test adding empty chunks list."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        count = backend.add_chunks([])
        self.assertEqual(count, 0)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("huf.ai.knowledge.backends.faiss_backend.VectorStoreIndex")
    def test_search(self, mock_index_class, mock_faiss_store_class):
        """Test searching the index."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        # Mock retriever and search results
        mock_node = MagicMock()
        mock_node.text = "Test result"
        mock_node.metadata = {
            "chunk_id": "chunk_1",
            "source_title": "Test Document",
            "knowledge_source": "test_source",
        }
        mock_node.score = 0.95
        
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_node]
        
        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever
        mock_index_class.from_documents.return_value = mock_index
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        # Add a chunk first
        chunks = [
            {
                "text": "Test chunk",
                "input_id": "doc_1",
                "input_type": "document",
                "chunk_id": "chunk_1",
                "source_title": "Test Document",
            }
        ]
        backend.add_chunks(chunks)
        
        # Search
        results = backend.search("test query", top_k=5)
        
        mock_retriever.retrieve.assert_called_once_with("test query")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "chunk_1")
        self.assertEqual(results[0].text, "Test result")
        self.assertEqual(results[0].score, 0.95)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    def test_delete_chunks(self, mock_faiss_store_class):
        """Test delete_chunks returns 0 (not implemented)."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        result = backend.delete_chunks("doc_1")
        self.assertEqual(result, 0)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_clear(self, mock_remove, mock_exists, mock_faiss_store_class):
        """Test clearing the index."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        mock_exists.return_value = True
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        backend.clear()
        
        mock_remove.assert_called_once_with(self.index_path)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("os.path.exists")
    def test_get_stats(self, mock_exists, mock_faiss_store_class):
        """Test getting backend statistics."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        mock_exists.return_value = True
        
        # Mock file size
        with patch("os.path.getsize", return_value=1024):
            backend = FAISSBackend()
            backend.initialize("test_source", self.config)
            
            stats = backend.get_stats()
            
            self.assertEqual(stats["backend_type"], "faiss")
            self.assertEqual(stats["knowledge_source"], "test_source")
            self.assertTrue(stats["initialized"])
            self.assertEqual(stats["index_path"], self.index_path)
            self.assertEqual(stats["dimension"], 384)
            self.assertTrue(stats["index_exists"])
            self.assertEqual(stats["index_file_size_bytes"], 1024)
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    def test_supports_filters(self, mock_faiss_store_class):
        """Test that filters are not supported."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        self.assertFalse(backend.supports_filters())
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    def test_supports_hybrid_search(self, mock_faiss_store_class):
        """Test that hybrid search is not supported."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        
        self.assertFalse(backend.supports_hybrid_search())
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    def test_health_check_uninitialized(self, mock_faiss_store_class):
        """Test health check when not initialized."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        backend = FAISSBackend()
        # Don't initialize
        
        is_healthy, message = backend.health_check()
        self.assertFalse(is_healthy)
        self.assertEqual(message, "Backend not initialized")
    
    @patch("huf.ai.knowledge.backends.faiss_backend.LLAMAINDEX_AVAILABLE", True)
    @patch("huf.ai.knowledge.backends.faiss_backend.FaissVectorStore")
    @patch("huf.ai.knowledge.backends.faiss_backend.VectorStoreIndex")
    def test_health_check_healthy(self, mock_index_class, mock_faiss_store_class):
        """Test health check when healthy."""
        mock_store = MagicMock()
        mock_faiss_store_class.return_value = mock_store
        
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        
        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever
        mock_index_class.from_documents.return_value = mock_index
        
        backend = FAISSBackend()
        backend.initialize("test_source", self.config)
        backend.add_chunks([{
            "text": "Test",
            "input_id": "doc_1",
            "input_type": "document",
        }])
        
        is_healthy, message = backend.health_check()
        self.assertTrue(is_healthy)
        self.assertEqual(message, "Healthy")


if __name__ == "__main__":
    unittest.main()
