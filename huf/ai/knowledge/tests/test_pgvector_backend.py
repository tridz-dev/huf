# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Mocked unit tests for PGVectorBackend index parameter selection."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends import pgvector_backend as pb
from huf.ai.knowledge.backends.pgvector_backend import PGVectorBackend


def _fake_from_params(*, use_halfvec=False, **kwargs):
	"""Stand-in whose signature advertises use_halfvec support."""


class TestPGVectorIndexParams(unittest.TestCase):
	def setUp(self):
		self.backend = PGVectorBackend()
		self.backend.config = {"index_type": "hnsw", "distance_metric": "cosine"}
		self.logger = MagicMock()
		p = patch.object(frappe, "logger", return_value=self.logger)
		p.start()
		self.addCleanup(p.stop)
		p = patch.object(PGVectorBackend, "_get_database_params", return_value={"host": "h"})
		p.start()
		self.addCleanup(p.stop)
		store = MagicMock()
		store.from_params = _fake_from_params
		p = patch.object(pb, "PGVectorStore", store)
		p.start()
		self.addCleanup(p.stop)

	def test_768_dims_unchanged(self):
		self.backend.dimension = 768
		with patch.object(PGVectorBackend, "_get_existing_embedding_column_type") as m:
			params = self.backend._get_connection_params()
		m.assert_not_called()
		self.assertEqual(params["hnsw_kwargs"]["hnsw_dist_method"], "vector_cosine_ops")
		self.assertEqual(params["hnsw_kwargs"]["hnsw_m"], 16)
		self.assertNotIn("use_halfvec", params)

	def test_3072_dims_new_table_uses_halfvec(self):
		self.backend.dimension = 3072
		with patch.object(PGVectorBackend, "_get_existing_embedding_column_type", return_value=None):
			params = self.backend._get_connection_params()
		self.assertTrue(params["use_halfvec"])
		self.assertEqual(params["hnsw_kwargs"]["hnsw_dist_method"], "halfvec_cosine_ops")

	def test_3072_dims_existing_vector_table_skips_index(self):
		self.backend.dimension = 3072
		with patch.object(PGVectorBackend, "_get_existing_embedding_column_type", return_value="vector"):
			params = self.backend._get_connection_params()
		self.assertNotIn("hnsw_kwargs", params)
		self.assertNotIn("use_halfvec", params)
		self.logger.warning.assert_called_once()
		self.assertIn("sequential", self.logger.warning.call_args[0][0])

	def test_3072_dims_inspection_failed_skips_index(self):
		"""An uninspectable table must not be assumed new (no halfvec request)."""
		self.backend.dimension = 3072
		with patch.object(PGVectorBackend, "_get_existing_embedding_column_type", return_value="unknown"):
			params = self.backend._get_connection_params()
		self.assertNotIn("hnsw_kwargs", params)
		self.assertNotIn("use_halfvec", params)

	def test_3072_dims_existing_halfvec_table_keeps_halfvec(self):
		self.backend.dimension = 3072
		with patch.object(PGVectorBackend, "_get_existing_embedding_column_type", return_value="halfvec"):
			params = self.backend._get_connection_params()
		self.assertTrue(params["use_halfvec"])
		self.assertIn("hnsw_kwargs", params)
