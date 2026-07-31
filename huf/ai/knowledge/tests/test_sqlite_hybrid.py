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

    def _extract_search_method(self, source: str) -> str:
        match = re.search(
            r'def search\([\s\S]*?\) -> List\[ChunkResult\]:\s*([\s\S]*?)(?=\n\s+def |\n\s+@|\Z)',
            source,
        )
        self.assertIsNotNone(match, "Could not locate search() method body")
        return match.group(1)

    def _extract_cte_branches(self, method_body: str):
        """Return (if_block, else_block) for the CTE-building if/else pair.

        The inner else: inside the filter loop is at deeper indentation, so we
        anchor the match to the same indentation as ``if filter_clauses:``.
        """
        match = re.search(
            r'(\n\s+)if filter_clauses:\s*(.*?)(\1else:)\s*(.*?)(?=\n\s+with self\._get_connection)',
            method_body,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not locate CTE-building if/else blocks")
        return match.group(2), match.group(4)

    def test_unfiltered_branch_uses_original_pre_b6_shape(self):
        """When filters are empty, keep the original vec/fts CTE shape (no JOIN, no where_sql)."""
        method_body = self._extract_search_method(self._read_search_source())
        _if_block, else_block = self._extract_cte_branches(method_body)

        # No chunks JOIN and no {where_sql} interpolation in the unfiltered CTEs.
        self.assertNotIn("JOIN chunks c", else_block)
        self.assertNotIn("{where_sql}", else_block)
        self.assertIn("FROM chunks_vec", else_block)
        self.assertIn("FROM chunks_fts", else_block)
        self.assertIn("WHERE embedding MATCH ?", else_block)
        self.assertIn("WHERE chunks_fts MATCH ?", else_block)
        self.assertIn("LIMIT 100", else_block)
        # Param order for the unfiltered branch.
        normalized = " ".join(else_block.split())
        self.assertIn(
            "params = [json.dumps(query_embedding), safe_fts_query, top_k]",
            normalized,
        )

    def test_filtered_branch_joins_chunks_and_applies_filters(self):
        """When filters are non-empty, JOIN chunks and apply metadata filters inside both CTEs."""
        method_body = self._extract_search_method(self._read_search_source())
        if_block, _else_block = self._extract_cte_branches(method_body)

        # Both CTEs JOIN chunks so filter expressions can reference c.* / c.metadata.
        self.assertEqual(if_block.count("JOIN chunks c"), 2)
        self.assertIn("{where_sql}", if_block)
        self.assertIn("v.embedding MATCH ?", if_block)
        self.assertIn("f.chunks_fts MATCH ?", if_block)
        self.assertIn("LIMIT 100", if_block)
        # Param order for the filtered branch.
        normalized = " ".join(if_block.split())
        self.assertIn(
            "[json.dumps(query_embedding)] + filter_values + [safe_fts_query] + filter_values + [top_k]",
            normalized,
        )

    def test_placeholder_count_matches_params_in_both_branches(self):
        """SQL placeholder count must equal length of params list in both branches."""
        method_body = self._extract_search_method(self._read_search_source())
        if_block, else_block = self._extract_cte_branches(method_body)

        # Unfiltered branch: vec MATCH ? + fts MATCH ? + final LIMIT ? = 3.
        else_placeholders = else_block.count("?") + 1  # + final LIMIT ?
        self.assertEqual(else_placeholders, 3)

        # Filtered branch: simulate expansion for N = 0, 1, 3 filters.
        vec_match = re.search(r'vec_cte_sql\s*=\s*f"""(.*?)"""', if_block, re.DOTALL)
        fts_match = re.search(r'fts_cte_sql\s*=\s*f"""(.*?)"""', if_block, re.DOTALL)
        self.assertIsNotNone(vec_match, "Could not extract filtered vec_cte_sql template")
        self.assertIsNotNone(fts_match, "Could not extract filtered fts_cte_sql template")
        vec_template = vec_match.group(1)
        fts_template = fts_match.group(1)

        for n in (0, 1, 3):
            clauses = [f"c.field_{i} = ?" for i in range(n)]
            where_sql = "" if not clauses else " AND " + " AND ".join(clauses)
            vec_total = vec_template.replace("{where_sql}", where_sql).count("?")
            fts_total = fts_template.replace("{where_sql}", where_sql).count("?")
            # vec + fts + final LIMIT ?
            total = vec_total + fts_total + 1
            expected = 2 * n + 3
            self.assertEqual(
                total, expected,
                f"Filtered branch with {n} filters expected {expected} placeholders, got {total}"
            )


@unittest.skipUnless(
    _RUNTIME_AVAILABLE,
    "sqlite-vec runtime tests skipped: sqlite-vec is not installed or this Python's "
    "sqlite3 was compiled without loadable extension support (OMIT_LOAD_EXTENSION). "
    "Static param-order tests above still run.",
)
@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
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
