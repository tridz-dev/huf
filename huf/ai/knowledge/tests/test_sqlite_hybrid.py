"""Tests for SQLiteHybridBackend (sqlite-vec + FTS5 RRF).

Run with: python3 -m pytest huf/ai/knowledge/tests/test_sqlite_hybrid.py -v
"""

import hashlib
import os
import re
import tempfile
import unittest
from unittest.mock import patch


SQLITE_HYBRID_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "backends", "sqlite_hybrid.py"
)


def _fake_embedding(text: str, dimension: int = 8) -> list:
    """Deterministic fixed-dimension embedding from text hash."""
    h = hashlib.sha256(str(text).encode("utf-8")).digest()
    vec = []
    for i in range(dimension):
        val = int.from_bytes(h[(i * 2) % len(h) : (i * 2 + 2) % len(h) or len(h)], "big")
        vec.append((val % 2000) / 1000.0 - 1.0)
    return vec


def _fake_embeddings(texts: list, dimension: int = 8) -> list:
    return [_fake_embedding(t, dimension) for t in texts]


def _can_run_sqlite_hybrid_runtime() -> bool:
    """Return True only if sqlite-vec is importable and this Python's sqlite3
    supports loadable extensions (required for vec0)."""
    try:
        import sqlite3
        import sqlite_vec  # noqa: F401

        conn = sqlite3.connect(":memory:")
        try:
            if not hasattr(conn, "enable_load_extension"):
                return False
            conn.enable_load_extension(True)
            conn.load_extension(sqlite_vec.loadable_path())
            return True
        finally:
            conn.close()
    except Exception:
        return False


_RUNTIME_AVAILABLE = _can_run_sqlite_hybrid_runtime()


class TestSQLiteHybridStatic(unittest.TestCase):
    """Static checks that do not require sqlite-vec to be loadable."""

    def _read_search_source(self) -> str:
        with open(SQLITE_HYBRID_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_param_placeholder_count_matches_derived_params(self):
        """B6 static regression: SQL placeholder count must match params list.

        The B6 fix moved metadata filters inside both CTEs. Param order is:
        [embedding] + filter_values + [fts_query] + filter_values + [top_k]
        For N filters, SQL has N placeholders in vec CTE, N in fts CTE, plus 3
        positional params (vec MATCH, fts MATCH, LIMIT). Total placeholders
        must equal 2*N + 3.
        """
        source = self._read_search_source()
        match = re.search(
            r'cursor = conn\.execute\(\s*f"""(.*?)"""\s*,\s*params\s*,?\s*\)',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not locate search SQL in sqlite_hybrid.py")
        sql_template = match.group(1)

        # Count literal ? placeholders in the SQL template (excluding {where_sql}).
        template_placeholders = sql_template.count("?")
        # The template should contain exactly 3 literal ?s:
        # vec MATCH ?, fts MATCH ?, final LIMIT ?
        self.assertEqual(template_placeholders, 3,
                         f"Expected 3 base placeholders, got {template_placeholders}")

        # Simulate N filter clauses and verify total placeholder count.
        for n in (0, 1, 3):
            clauses = [f"c.field_{i} = ?" for i in range(n)]
            where_sql = "" if not clauses else " AND " + " AND ".join(clauses)
            expanded = sql_template.replace("{where_sql}", where_sql)
            total = expanded.count("?")
            expected = 3 + 2 * n
            self.assertEqual(
                total, expected,
                f"For {n} filters expected {expected} placeholders, got {total}"
            )

    def test_vec_cte_has_join_and_limit(self):
        """B6 fix joined chunks inside the vec KNN CTE and kept LIMIT."""
        source = self._read_search_source()
        match = re.search(r'WITH vec_results AS \((.*?)\),\s*fts_results AS', source, re.DOTALL)
        self.assertIsNotNone(match)
        vec_cte = match.group(1)
        self.assertIn("JOIN chunks c", vec_cte)
        self.assertIn("LIMIT 100", vec_cte)
        self.assertIn("v.embedding MATCH ?", vec_cte)
        self.assertIn("{where_sql}", vec_cte)

    def test_fts_cte_has_join_and_limit(self):
        """B6 fix joined chunks inside the FTS CTE and kept LIMIT."""
        source = self._read_search_source()
        match = re.search(r'fts_results AS \((.*?)\),\s*combined AS', source, re.DOTALL)
        self.assertIsNotNone(match)
        fts_cte = match.group(1)
        self.assertIn("JOIN chunks c", fts_cte)
        self.assertIn("LIMIT 100", fts_cte)
        self.assertIn("f.chunks_fts MATCH ?", fts_cte)
        self.assertIn("{where_sql}", fts_cte)


@unittest.skipUnless(
    _RUNTIME_AVAILABLE,
    "sqlite-vec runtime tests skipped: sqlite-vec is not installed or this Python's "
    "sqlite3 was compiled without loadable extension support (OMIT_LOAD_EXTENSION). "
    "Static param-order tests above still run.",
)
class TestSQLiteHybridRuntime(unittest.TestCase):
    """Runtime tests for SQLiteHybridBackend.

    These require sqlite-vec + a Python sqlite3 with loadable extension support.
    They are skipped in environments where that is unavailable.
    """

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tempdir, "test_hybrid.sqlite3")

        # Patch Frappe filesystem helpers
        self.files_path_patcher = patch(
            "huf.ai.knowledge.backends.sqlite_hybrid.get_files_path"
        )
        self.mock_get_files_path = self.files_path_patcher.start()
        self.mock_get_files_path.return_value = self.tempdir

        self.scrub_patcher = patch("huf.ai.knowledge.backends.sqlite_hybrid.frappe.scrub")
        self.mock_scrub = self.scrub_patcher.start()
        self.mock_scrub.side_effect = lambda x: re.sub(r"[^a-z0-9]", "_", str(x).lower())

        # Patch embedding functions to deterministic offline fakes
        self.patcher_config = patch(
            "huf.ai.knowledge.backends.sqlite_hybrid.resolve_embedding_config"
        )
        self.mock_resolve = self.patcher_config.start()
        self.mock_resolve.return_value = {
            "model": "test-model",
            "api_key": "test",
            "api_base": "test",
        }

        self.patcher_embeds = patch("huf.ai.knowledge.backends.sqlite_hybrid.get_embeddings")
        self.mock_get_embeds = self.patcher_embeds.start()
        self.mock_get_embeds.side_effect = lambda texts, **kwargs: _fake_embeddings(texts, dimension=8)

        self.patcher_embed = patch("huf.ai.knowledge.backends.sqlite_hybrid.get_embedding")
        self.mock_get_embed = self.patcher_embed.start()
        self.mock_get_embed.side_effect = lambda text, **kwargs: _fake_embedding(text, dimension=8)

        from huf.ai.knowledge.backends.sqlite_hybrid import SQLiteHybridBackend

        self.backend = SQLiteHybridBackend()
        self.backend.initialize("test_source", {"vector_dimension": 8})

    def tearDown(self):
        self.files_path_patcher.stop()
        self.scrub_patcher.stop()
        self.patcher_config.stop()
        self.patcher_embeds.stop()
        self.patcher_embed.stop()
        if self.backend and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def _seed_chunks(self):
        """Insert ~20 chunks split between category a and category b."""
        chunks = []
        for i in range(10):
            chunks.append({
                "chunk_id": f"a_chunk_{i}",
                "input_id": f"input_a_{i % 3}",
                "input_type": "document",
                "source_title": f"Alpha doc {i % 3}",
                "chunk_index": i,
                "text": f"Alpha content about topic alpha number {i}.",
                "metadata": {"category": "a", "idx": i},
            })
            chunks.append({
                "chunk_id": f"b_chunk_{i}",
                "input_id": f"input_b_{i % 3}",
                "input_type": "document",
                "source_title": f"Beta doc {i % 3}",
                "chunk_index": i,
                "text": f"Beta content about topic beta number {i}.",
                "metadata": {"category": "b", "idx": i},
            })
        self.backend.add_chunks(chunks)

    def test_unfiltered_hybrid_search_returns_top_k(self):
        """Unfiltered search returns up to top_k results."""
        self._seed_chunks()
        results = self.backend.search("alpha", top_k=5)
        self.assertLessEqual(len(results), 5)
        self.assertGreater(len(results), 0)

    def test_filtered_hybrid_search_returns_top_k_of_category(self):
        """B6 regression: filtered search must return top_k category-a results."""
        self._seed_chunks()
        results = self.backend.search("content", top_k=5, filters={"category": "a"})
        self.assertLessEqual(len(results), 5)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r.metadata.get("category"), "a",
                             f"Expected only category-a results, got {r.metadata}")

    def test_sql_param_count_no_binding_error(self):
        """The search query executes without parameter binding errors."""
        self._seed_chunks()
        # This would raise sqlite3.ProgrammingError if placeholders != params.
        results = self.backend.search("number", top_k=3, filters={"category": "a"})
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
