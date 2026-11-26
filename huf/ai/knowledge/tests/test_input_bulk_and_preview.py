"""Bulk input delete and indexed-text preview (frappe mocked; runs bench-less and on a bench)."""

import importlib
import os
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends import ChunkResult, KnowledgeBackend
from huf.ai.knowledge.backends.chunk_listing import page_chunks, sql_chunks, to_result


def _load_api():
	"""Import the API module with ``frappe.whitelist`` as a pass-through (it is a stub without a bench)."""
	if isinstance(frappe.whitelist, MagicMock):
		with patch.object(frappe, "whitelist", lambda *a, **k: (lambda fn: fn)):
			return importlib.reload(importlib.import_module("huf.ai.knowledge.api.inputs"))
	return importlib.import_module("huf.ai.knowledge.api.inputs")


api = _load_api()


class StoreDown(Exception):
	pass


class PermissionDenied(Exception):
	pass


class FakeFrappe:
	"""Just enough of ``frappe`` for the API module."""

	PermissionError = PermissionDenied

	def __init__(self, owners, allowed=None, allow_source=True):
		self.owners = owners  # input name -> knowledge source
		self.allowed = set(owners) if allowed is None else set(allowed)
		self.allow_source = allow_source
		self.deleted = []
		self.rolled_back = []
		self.trash_flags = []
		self.db = types.SimpleNamespace(
			get_value=lambda dt, name, field: self.owners.get(name),
			savepoint=lambda name: None,
			rollback=lambda save_point=None: self.rolled_back.append(save_point),
		)
		self.logged = []

	def has_permission(self, doctype, ptype="read", doc=None):
		if doctype == "Knowledge Source":
			return self.allow_source
		return doc is None or doc in self.allowed

	def throw(self, message, exc=None):
		raise (exc or ValueError)(message)

	def get_doc(self, doctype, name):
		if doctype == "Knowledge Source":
			return types.SimpleNamespace(name=name, knowledge_type="sqlite_fts")
		return types.SimpleNamespace(doctype=doctype, name=name)

	def delete_doc(self, doctype, name, ignore_on_trash=False):
		self.deleted.append(name)
		self.trash_flags.append(ignore_on_trash)

	def get_doc_hooks(self):
		return {"Knowledge Input": {"on_trash": [api.CLEANUP_HOOK]}, "*": {"on_trash": ["x.other"]}}

	def get_attr(self, path):
		return lambda doc, method: self.logged.append(("hook", path, doc.name))

	def log_error(self, **kw):
		self.logged.append(("error", kw))

	get_traceback = staticmethod(lambda: "tb")
	whitelist = staticmethod(lambda *a, **k: (lambda fn: fn))


class FakeBackend:
	def __init__(self, fail_on=()):
		self.fail_on = set(fail_on)
		self.removed = []

	def delete_chunks(self, input_id):
		if input_id in self.fail_on:
			raise StoreDown
		self.removed.append(input_id)
		return 1


def _run_bulk(fake, inputs, backend=None):
	backend = backend or FakeBackend()
	stats = MagicMock()
	status = MagicMock()
	with (
		patch.object(api, "frappe", fake),
		patch.object(api, "_", lambda s: s),
		patch.object(api, "_open_backend", lambda source: backend),
		patch("huf.ai.knowledge.indexer.update_source_stats", stats),
		patch("huf.ai.knowledge.hooks.recompute_source_status", status),
	):
		result = api.bulk_delete_inputs("KS", inputs)
	return result, backend, stats, status


class TestBulkDelete(unittest.TestCase):
	def test_deletes_all_and_refreshes_stats_once(self):
		fake = FakeFrappe({"A": "KS", "B": "KS", "C": "KS"})
		result, backend, stats, status = _run_bulk(fake, '["A", "B", "C", "A"]')
		self.assertEqual(result, {"deleted": ["A", "B", "C"], "failed": []})
		self.assertEqual(backend.removed, ["A", "B", "C"])
		self.assertEqual(fake.deleted, ["A", "B", "C"])
		self.assertEqual(fake.trash_flags, [True, True, True])
		stats.assert_called_once()
		status.assert_called_once_with("KS")
		# the per-input cleanup hook is skipped, other on_trash hooks still run
		hooks = [e for e in fake.logged if e[0] == "hook"]
		self.assertEqual({h[1] for h in hooks}, {"x.other"})

	def test_permission_checked_per_row(self):
		fake = FakeFrappe({"A": "KS", "B": "KS"}, allowed={"A"})
		result, backend, _stats, _status = _run_bulk(fake, ["A", "B"])
		self.assertEqual(result["deleted"], ["A"])
		self.assertEqual(result["failed"][0]["name"], "B")
		self.assertEqual(backend.removed, ["A"])
		self.assertEqual(fake.deleted, ["A"])

	def test_rows_of_other_sources_are_refused(self):
		fake = FakeFrappe({"A": "KS", "Z": "OTHER"})
		result, _backend, _stats, _status = _run_bulk(fake, ["A", "Z", "missing"])
		self.assertEqual(result["deleted"], ["A"])
		self.assertEqual([f["name"] for f in result["failed"]], ["Z", "missing"])

	def test_failed_row_is_rolled_back_and_reported(self):
		fake = FakeFrappe({"A": "KS", "B": "KS"})
		result, _backend, stats, _status = _run_bulk(fake, ["A", "B"], FakeBackend(fail_on={"A"}))
		self.assertEqual(result["deleted"], ["B"])
		self.assertEqual(result["failed"][0]["name"], "A")
		self.assertEqual(len(fake.rolled_back), 1)
		stats.assert_called_once()

	def test_nothing_deleted_means_no_stats_refresh(self):
		fake = FakeFrappe({"A": "KS"}, allowed=set())
		result, _backend, stats, status = _run_bulk(fake, ["A"])
		self.assertEqual(result["deleted"], [])
		stats.assert_not_called()
		status.assert_not_called()

	def test_source_permission_is_required(self):
		fake = FakeFrappe({"A": "KS"}, allow_source=False)
		with self.assertRaises(PermissionDenied):
			_run_bulk(fake, ["A"])
		self.assertEqual(fake.deleted, [])

	def test_rejects_bad_input_lists(self):
		fake = FakeFrappe({})
		for bad in ("not json", [], "[1]", {"a": 1}):
			with self.assertRaises(ValueError):
				_run_bulk(fake, bad)
		with self.assertRaises(ValueError):
			_run_bulk(fake, [f"I{i}" for i in range(api.MAX_BULK_DELETE + 1)])


class FakePreviewBackend:
	def __init__(self, listed):
		self.listed = listed

	def get_chunks(self, input_id, start, limit):
		return self.listed


def _preview(fake, backend, **kw):
	with (
		patch.object(api, "frappe", fake),
		patch.object(api, "_", lambda s: s),
		patch.object(api, "_open_backend", lambda source: backend),
	):
		return api.get_input_chunks("A", **kw)


class TestPreview(unittest.TestCase):
	def test_returns_a_page(self):
		fake = FakeFrappe({"A": "KS"})
		chunk = ChunkResult(chunk_id="c", text="hello", metadata={"chunk_index": 3, "page": 2})
		out = _preview(fake, FakePreviewBackend(([chunk], 9)), start=2, limit=1)
		self.assertEqual(out["total"], 9)
		self.assertTrue(out["supported"])
		self.assertEqual(out["chunks"], [{"index": 3, "text": "hello", "page": 2, "page_end": None}])

	def test_unsupported_backend_says_so(self):
		out = _preview(FakeFrappe({"A": "KS"}), FakePreviewBackend(None))
		self.assertFalse(out["supported"])
		self.assertEqual(out["chunks"], [])

	def test_read_permission_on_source_is_enforced(self):
		with self.assertRaises(PermissionDenied):
			_preview(FakeFrappe({"A": "KS"}, allow_source=False), FakePreviewBackend(([], 0)))

	def test_read_permission_on_input_is_enforced(self):
		with self.assertRaises(PermissionDenied):
			_preview(FakeFrappe({"A": "KS"}, allowed=set()), FakePreviewBackend(([], 0)))

	def test_unknown_input_is_denied(self):
		with self.assertRaises(PermissionDenied):
			_preview(FakeFrappe({}), FakePreviewBackend(([], 0)))

	def test_page_size_is_capped(self):
		seen = {}

		class Spy(FakePreviewBackend):
			def get_chunks(self, input_id, start, limit):
				seen.update(start=start, limit=limit)
				return [], 0

		_preview(FakeFrappe({"A": "KS"}), Spy(None), start=-5, limit=100000)
		self.assertEqual(seen, {"start": 0, "limit": api.MAX_PAGE_SIZE})


class TestChunkListing(unittest.TestCase):
	def test_base_backend_cannot_list(self):
		self.assertIsNone(KnowledgeBackend.get_chunks(MagicMock(), "A"))

	def test_page_chunks_orders_and_slices(self):
		chunks = [to_result(str(i), f"t{i}", {}, None, i) for i in (2, 0, 1, 3)]
		page, total = page_chunks(chunks, 1, 2)
		self.assertEqual([c.text for c in page], ["t1", "t2"])
		self.assertEqual(total, 4)

	def test_sql_chunks_pages_one_input_only(self):
		conn = sqlite3.connect(":memory:")
		conn.row_factory = sqlite3.Row
		conn.execute(
			"CREATE TABLE chunks (chunk_id TEXT, input_id TEXT, source_title TEXT, chunk_index INTEGER, text TEXT, metadata TEXT)"
		)
		for i in range(5):
			conn.execute(
				"INSERT INTO chunks VALUES (?, 'A', 'T', ?, ?, ?)", (f"a{i}", i, f"body {i}", '{"page": 4}')
			)
		conn.execute("INSERT INTO chunks VALUES ('b0', 'B', 'T', 0, 'other', NULL)")
		page, total = sql_chunks(conn, "A", 3, 10)
		self.assertEqual(total, 5)
		self.assertEqual([c.text for c in page], ["body 3", "body 4"])
		self.assertEqual(page[0].metadata, {"page": 4, "chunk_index": 3})

	def test_sqlite_fts_backend_lists_real_chunks(self):
		from huf.ai.knowledge.backends.sqlite_fts import SQLiteFTSBackend

		with tempfile.TemporaryDirectory() as tmp:
			backend = SQLiteFTSBackend()
			backend.db_path = os.path.join(tmp, "k.sqlite3")
			with backend._get_connection() as conn:
				conn.executescript(backend._schema)
			backend.add_chunks(
				[
					{"input_id": "A", "input_type": "Text", "chunk_index": i, "text": f"part {i}"}
					for i in (1, 0, 2)
				]
				+ [{"input_id": "B", "input_type": "Text", "chunk_index": 0, "text": "other"}]
			)
			page, total = backend.get_chunks("A", 0, 2)
			self.assertEqual((total, [c.text for c in page]), (3, ["part 0", "part 1"]))
			self.assertEqual(backend.get_chunks("none", 0, 5), ([], 0))

	def test_faiss_lists_from_sidecar(self):
		from huf.ai.knowledge.backends.faiss_backend import FaissBackend

		backend = FaissBackend()
		backend._initialized = True
		backend._chunk_store = {
			"0": {"chunk_id": "x", "text": "second", "metadata": {"input_id": "A", "chunk_index": 1}},
			"1": {"chunk_id": "y", "text": "first", "metadata": {"input_id": "A", "chunk_index": 0}},
			"2": {"chunk_id": "z", "text": "foreign", "metadata": {"input_id": "B", "chunk_index": 0}},
		}
		page, total = backend.get_chunks("A", 0, 10)
		self.assertEqual((total, [c.text for c in page]), (2, ["first", "second"]))

	def test_chroma_lists_from_collection(self):
		from huf.ai.knowledge.backends.chroma_backend import ChromaBackend

		backend = ChromaBackend()
		backend._initialized = True
		backend.collection = MagicMock()
		backend.collection.get.return_value = {
			"ids": ["b", "a"],
			"documents": ["two", "one"],
			"metadatas": [{"chunk_index": 1, "source_title": "T"}, {"chunk_index": 0, "source_title": "T"}],
		}
		page, total = backend.get_chunks("A", 0, 10)
		self.assertEqual((total, [c.text for c in page]), (2, ["one", "two"]))
		self.assertEqual(page[0].title, "T")
