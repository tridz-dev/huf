# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Bench-less tests for bulk ingestion sources: safety helpers (pure) plus
S3 / SFTP scanners and start_import validation with frappe/boto3/paramiko mocked.
Anything touching the DB, redis or the queue needs a live bench."""

import importlib
import io
import os
import stat
import sys
import types
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from huf.ai.knowledge.sources.safety import (
	Limits,
	SourceSafetyError,
	classify,
	expand_zip,
	is_within,
	load_limits,
	resolve_under_roots,
	safe_member_path,
	walk_directory,
)


def _zip(path, members):
	with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
		for name, data in members.items():
			zf.writestr(name, data)


class TestPathContainment:
	def test_inside_and_root_itself(self, tmp_path):
		(tmp_path / "a").mkdir()
		assert is_within(str(tmp_path / "a"), str(tmp_path))
		assert is_within(str(tmp_path), str(tmp_path))

	def test_sibling_prefix_is_outside(self, tmp_path):
		(tmp_path / "root").mkdir()
		(tmp_path / "root2").mkdir()
		assert not is_within(str(tmp_path / "root2"), str(tmp_path / "root"))

	def test_dotdot_escape(self, tmp_path):
		(tmp_path / "root").mkdir()
		assert not is_within(str(tmp_path / "root" / ".." ), str(tmp_path / "root"))

	def test_symlink_escape_resolved(self, tmp_path):
		root, outside = tmp_path / "root", tmp_path / "outside"
		root.mkdir()
		outside.mkdir()
		os.symlink(outside, root / "link")
		assert not is_within(str(root / "link"), str(root))
		with pytest.raises(PermissionError):
			resolve_under_roots(str(root / "link"), [str(root)])

	def test_resolve_ok_and_rejections(self, tmp_path):
		(tmp_path / "d").mkdir()
		assert resolve_under_roots(str(tmp_path / "d"), [str(tmp_path)]) == os.path.realpath(tmp_path / "d")
		with pytest.raises(PermissionError):
			resolve_under_roots(str(tmp_path / "d"), [])  # no roots configured
		with pytest.raises(PermissionError):
			resolve_under_roots("relative/path", [str(tmp_path)])
		with pytest.raises(PermissionError):
			resolve_under_roots("/etc", [str(tmp_path)])

	def test_walk_skips_symlinks(self, tmp_path):
		root, outside = tmp_path / "root", tmp_path / "outside"
		root.mkdir()
		outside.mkdir()
		(root / "ok.txt").write_text("hi")
		(outside / "secret.txt").write_text("no")
		os.symlink(outside / "secret.txt", root / "leak.txt")
		os.symlink(outside, root / "dirlink")
		found = [rel for rel, _p, _s in walk_directory(str(root), Limits())]
		assert found == ["ok.txt"]


class TestZipSafety:
	@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../evil.txt", "C:/x.txt", "..\\evil.txt", ""])
	def test_unsafe_member_names(self, name):
		assert safe_member_path(name) is None

	def test_safe_member_names(self):
		assert safe_member_path("a/b.txt") == "a/b.txt"
		assert safe_member_path("./a//b.txt") == "a/b.txt"

	def test_zip_slip_blocked_not_written(self, tmp_path):
		z = tmp_path / "evil.zip"
		_zip(z, {"../escape.txt": "x", "ok.txt": "fine"})
		res = expand_zip(str(z), str(tmp_path / "out"), Limits())
		assert [f.rel for f in res.files] == ["ok.txt"]
		assert res.blocked and res.blocked[0][1] == "unsafe path"
		assert not (tmp_path / "escape.txt").exists()

	def test_symlink_member_blocked(self, tmp_path):
		z = tmp_path / "s.zip"
		with zipfile.ZipFile(z, "w") as zf:
			info = zipfile.ZipInfo("link.txt")
			info.external_attr = (stat.S_IFLNK | 0o777) << 16
			zf.writestr(info, "/etc/passwd")
			zf.writestr("real.txt", "ok")
		res = expand_zip(str(z), str(tmp_path / "out"), Limits())
		assert [f.rel for f in res.files] == ["real.txt"]
		assert res.blocked == [("link.txt", "symlink")]

	def test_zip_bomb_declared_size_cap(self, tmp_path):
		z = tmp_path / "bomb.zip"
		_zip(z, {"big.txt": b"0" * 200_000})
		limits = Limits(max_uncompressed_bytes=100_000)
		with pytest.raises(SourceSafetyError):
			expand_zip(str(z), str(tmp_path / "out"), limits)

	def test_zip_bomb_cumulative_cap(self, tmp_path):
		z = tmp_path / "many.zip"
		_zip(z, {f"f{i}.txt": b"0" * 40_000 for i in range(5)})
		with pytest.raises(SourceSafetyError):
			expand_zip(str(z), str(tmp_path / "out"), Limits(max_uncompressed_bytes=100_000))

	def test_streaming_cap_when_header_lies(self, tmp_path):
		z = tmp_path / "lie.zip"
		_zip(z, {"a.txt": b"0" * 50_000})
		real_info = zipfile.ZipFile.infolist

		def lying(self):
			infos = real_info(self)
			for i in infos:
				i.file_size = 1  # header claims 1 byte
			return infos

		with patch.object(zipfile.ZipFile, "infolist", lying):
			with pytest.raises(SourceSafetyError):
				expand_zip(str(z), str(tmp_path / "out"), Limits(max_uncompressed_bytes=10_000))

	def test_nested_zip_expanded_with_prefix(self, tmp_path):
		inner = io.BytesIO()
		with zipfile.ZipFile(inner, "w") as zf:
			zf.writestr("deep.md", "# hi")
			zf.writestr("deep.exe", "MZ")
		z = tmp_path / "outer.zip"
		_zip(z, {"inner.zip": inner.getvalue(), "top.txt": "t"})
		res = expand_zip(str(z), str(tmp_path / "out"), Limits(), prefix="outer.zip/")
		by_rel = {f.rel: f for f in res.files}
		assert set(by_rel) == {"outer.zip/top.txt", "outer.zip/inner.zip/deep.md", "outer.zip/inner.zip/deep.exe"}
		assert by_rel["outer.zip/inner.zip/deep.exe"].skip_reason == "Unsupported"
		assert open(by_rel["outer.zip/inner.zip/deep.md"].path).read() == "# hi"

	def test_nesting_depth_limit(self, tmp_path):
		data = b"x"
		name = "t.txt"
		payload = {name: data}
		blob = None
		for level in range(5):
			buf = io.BytesIO()
			with zipfile.ZipFile(buf, "w") as zf:
				for n, d in payload.items():
					zf.writestr(n, d)
			blob = buf.getvalue()
			payload = {"z.zip": blob}
		z = tmp_path / "deep.zip"
		z.write_bytes(blob)
		res = expand_zip(str(z), str(tmp_path / "out"), Limits(max_zip_depth=2))
		assert any(reason == "zip nested too deeply" for _n, reason in res.blocked)


class TestClassification:
	def test_extension_and_size(self):
		limits = Limits(max_file_bytes=100, extensions=(".pdf", ".txt"))
		assert classify("a.PDF", 10, limits) is None
		assert classify("a.exe", 10, limits) == "Unsupported"
		assert classify("a.pdf", 101, limits) == "Too Large"
		assert classify("a.exe", 10_000, limits) == "Unsupported"  # extension wins
		assert classify("noext", 1, limits) == "Unsupported"
		assert classify("a.pdf", 100, limits) is None

	def test_load_limits_defaults_and_overrides(self):
		d = load_limits({})
		assert d.max_file_bytes == 50 * 1024 * 1024 and d.max_files == 1000
		c = load_limits({"huf_bulk_max_file_mb": 2, "huf_bulk_max_files": 5, "huf_bulk_allowed_extensions": ["PDF", ".txt"]})
		assert c.max_file_bytes == 2 * 1024 * 1024 and c.max_files == 5 and c.extensions == (".pdf", ".txt")
		assert load_limits({"huf_bulk_max_files": "bogus"}).max_files == 1000


def _scan_ctx(max_files=1000):
	from huf.ai.knowledge.sources import scanners as bulk_sources

	ctx = bulk_sources.ScanContext("ING-1", "KS-1", Limits(max_files=max_files, max_file_bytes=1000))
	ctx.touch = MagicMock()  # heartbeat writes need a DB; tested separately
	return bulk_sources, ctx


def _fake_file(counter=[0]):
	counter[0] += 1
	return types.SimpleNamespace(name=f"F{counter[0]}", file_url=f"/private/files/f{counter[0]}")


class TestBlockedZipMembersVisible:
	def test_blocked_members_recorded_as_unsafe(self, tmp_path):
		z = tmp_path / "evil.zip"
		blob = b"t"
		for _ in range(4):  # zip nested 4 deep
			buf = io.BytesIO()
			with zipfile.ZipFile(buf, "w") as zf:
				zf.writestr("t.txt" if blob == b"t" else "z.zip", blob)
			blob = buf.getvalue()
		_zip(z, {"../evil.txt": "x", "/abs/path.txt": "y", "deep.zip": blob, "ok.txt": "fine"})
		bulk_sources, ctx = _scan_ctx()
		ctx.add_local = MagicMock()
		res = expand_zip(str(z), str(tmp_path / "out"), Limits(max_zip_depth=2))
		bulk_sources._add_expanded(ctx, res)
		unsafe = [e for e in ctx.entries if e["skip_reason"] == "Unsafe"]
		assert len(unsafe) == len(res.blocked) >= 3
		keys = " ".join(e["external_key"] for e in unsafe)
		assert "../evil.txt" in keys and "/abs/path.txt" in keys
		assert all(e["file"] is None and len(e["external_key"]) <= 255 for e in unsafe)
		ctx.add_local.assert_called_once()
		assert ctx.add_local.call_args[0][0] == "ok.txt"
		assert not (tmp_path / "evil.txt").exists()

	def test_long_unsafe_name_truncated(self):
		bulk_sources, ctx = _scan_ctx()
		res = types.SimpleNamespace(files=[], blocked=[("../" + "a" * 600, "path escapes destination")])
		bulk_sources._add_expanded(ctx, res)
		assert len(ctx.entries[0]["external_key"]) <= 255
		assert ctx.entries[0]["skip_reason"] == "Unsafe"


class TestS3Scan:
	def _install_s3(self, pages, downloads):
		mod = types.ModuleType("huf.ai.tools.s3")
		mod.get_s3_client = MagicMock(return_value="client")
		calls = []

		def list_page(client, bucket, prefix="", continuation_token=None, page_size=1000):
			calls.append(continuation_token)
			return pages[len(calls) - 1]

		mod.list_objects_page = list_page
		mod.download_object = MagicMock(side_effect=lambda c, b, k, m: downloads[k])
		return mod, calls

	def test_pagination_into_entries(self):
		pages = [
			{"objects": [{"key": "a.pdf", "size": 10}, {"key": "b.exe", "size": 5}], "next_token": "t1"},
			{"objects": [{"key": "c.txt", "size": 5000}, {"key": "d/e.md", "size": 3}], "next_token": None},
		]
		mod, calls = self._install_s3(pages, {"a.pdf": b"PDF", "d/e.md": b"# e"})
		bulk_sources, ctx = _scan_ctx()
		with patch.dict(sys.modules, {"huf.ai.tools.s3": mod}), patch.object(
			bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()
		):
			bulk_sources.scan_s3(ctx, {"bucket": "bk", "prefix": "docs/"})
		assert calls == [None, "t1"]
		by_key = {e["external_key"]: e for e in ctx.entries}
		assert set(by_key) == {"s3://bk/a.pdf", "s3://bk/b.exe", "s3://bk/c.txt", "s3://bk/d/e.md"}
		assert by_key["s3://bk/b.exe"]["skip_reason"] == "Unsupported"
		assert by_key["s3://bk/c.txt"]["skip_reason"] == "Too Large"
		assert by_key["s3://bk/a.pdf"]["file"] and len(by_key["s3://bk/a.pdf"]["checksum"]) == 64
		mod.download_object.assert_any_call("client", "bk", "a.pdf", 1000)

	def test_max_files_truncates(self):
		pages = [{"objects": [{"key": f"{i}.txt", "size": 1} for i in range(5)], "next_token": None}]
		mod, _calls = self._install_s3(pages, {f"{i}.txt": b"x" for i in range(5)})
		bulk_sources, ctx = _scan_ctx(max_files=2)
		with patch.dict(sys.modules, {"huf.ai.tools.s3": mod}), patch.object(
			bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()
		):
			bulk_sources.scan_s3(ctx, {"bucket": "bk"})
		assert len(ctx.entries) == 2 and ctx.truncated


class TestEmptyContent:
	def test_zero_byte_content_is_skipped_not_a_file_doc(self):
		bulk_sources, ctx = _scan_ctx()
		with patch.object(bulk_sources, "make_private_file") as make_file:
			ctx.add_content("empty.txt", "empty.txt", b"")
		make_file.assert_not_called()
		assert ctx.entries == [
			{"file": None, "file_url": None, "external_key": "empty.txt", "checksum": None, "skip_reason": "No Text"}
		]


class TestExternalKeys:
	def test_short_key_unchanged_and_long_key_deterministic(self):
		from huf.ai.knowledge.sources.scanners import make_external_key

		assert make_external_key("a.txt") == "a.txt"
		long_a, long_b = "s3://b/" + "x" * 400 + "A", "s3://b/" + "x" * 400 + "B"
		ka, kb = make_external_key(long_a), make_external_key(long_a)
		assert ka == kb and len(ka) == 190 + 1 + 40 and ka[190] == "#"
		assert make_external_key(long_b) != ka  # same 190-char prefix, distinct hash

	def test_add_skip_truncates_like_add_content(self):
		bulk_sources, ctx = _scan_ctx()
		ctx.add_skip("k" * 400, "Unsupported")
		assert ctx.entries[0]["external_key"] == bulk_sources.make_external_key("k" * 400)
		assert len(ctx.entries[0]["external_key"]) <= 255

	def test_same_named_uploads_get_distinct_keys(self):
		bulk_sources, ctx = _scan_ctx()
		for docname in ("FILE-1", "FILE-2"):
			doc = types.SimpleNamespace(
				name=docname, file_name="notes.pdf", file_size=3, is_private=1, file_url=f"/private/{docname}",
				get_content=lambda: b"abc",
			)
			bulk_sources.scan_file_doc(ctx, doc)
		keys = [e["external_key"] for e in ctx.entries]
		assert keys == ["upload://FILE-1", "upload://FILE-2"]

	def test_zip_keys_use_file_docname_and_nest(self, tmp_path):
		bulk_sources, ctx = _scan_ctx()
		inner = io.BytesIO()
		with zipfile.ZipFile(inner, "w") as z:
			z.writestr("deep.txt", "hi")
		outer = io.BytesIO()
		with zipfile.ZipFile(outer, "w") as z:
			z.writestr("a/b.txt", "yo")
			z.writestr("in.zip", inner.getvalue())
		doc = types.SimpleNamespace(name="FILE-9", file_name="bundle.zip", file_size=1, is_private=1, get_content=lambda: outer.getvalue())
		with patch.object(bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()):
			bulk_sources.scan_file_doc(ctx, doc)
		assert {e["external_key"] for e in ctx.entries} == {"zip://FILE-9/a/b.txt", "zip://FILE-9/in.zip/deep.txt"}


class TestScanCleanup:
	def test_created_files_deleted_on_failure_but_uploads_kept(self):
		bulk_sources, ctx = _scan_ctx()
		with patch.object(bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()):
			ctx.add_content("k1", "a.txt", b"a")
		ctx.entries.append({"file": "USER-UPLOAD", "file_url": "/x", "external_key": "upload://USER-UPLOAD", "checksum": "c"})
		boom = MagicMock(side_effect=RuntimeError("boom"))
		fake_frappe = MagicMock()
		fake_frappe.db.get_value.return_value = "KS-1"
		with patch.object(bulk_sources, "frappe", fake_frappe), patch.object(bulk_sources, "now_datetime", return_value=__import__("datetime").datetime(2026, 1, 1)), patch.object(bulk_sources, "load_limits", return_value=ctx.limits), patch.object(
			bulk_sources, "ScanContext", return_value=ctx
		), patch.dict(bulk_sources.SCANNERS, {"Upload": boom}):
			result = bulk_sources.run_scan("ING-1", "Upload", {})
		assert result["status"] == "failed"
		deleted = [c.args[1] for c in fake_frappe.delete_doc.call_args_list]
		assert deleted == [ctx.entries[0]["file"]] and "USER-UPLOAD" not in deleted
		fake_frappe.delete_doc.assert_called_with("File", deleted[0], ignore_permissions=True, force=True)
		fake_frappe.db.commit.assert_called()

	def test_finish_scan_cancelled_deletes_created_files(self):
		bulk_sources, _ctx = _scan_ctx()
		fake_frappe = MagicMock()
		fake_frappe.db.get_value.return_value = "Cancelled"
		with patch.object(bulk_sources, "frappe", fake_frappe), patch.object(bulk_sources, "now_datetime", return_value=__import__("datetime").datetime(2026, 1, 1)):
			out = bulk_sources.finish_scan("ING-1", [{"file": "F1", "external_key": "k"}], created_files=["F1"])
		assert out == {"status": "cancelled"}
		fake_frappe.delete_doc.assert_called_once_with("File", "F1", ignore_permissions=True, force=True)


class TestCancelledScan:
	def test_cancelled_header_stops_scan_and_no_more_writes(self):
		bulk_sources, ctx = _scan_ctx()
		fake_frappe = MagicMock()
		fake_frappe.db.get_value.return_value = "KS-1"
		fake_frappe.db._cursor.rowcount = 0  # header no longer Scanning
		visited = []

		def walker(c, _cfg):
			with patch.object(bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()):
				for i in range(100):
					visited.append(i)
					c.add_content(f"k{i}", f"a{i}.txt", b"a")

		with patch.object(bulk_sources, "frappe", fake_frappe), patch.object(bulk_sources, "load_limits", return_value=ctx.limits), patch.object(
			bulk_sources, "ScanContext", return_value=ctx
		), patch.dict(bulk_sources.SCANNERS, {"Upload": walker}):
			out = bulk_sources.run_scan("ING-1", "Upload", {})
		assert out == {"status": "cancelled"}
		assert len(visited) == 10  # stopped at the first heartbeat
		beats = [c for c in fake_frappe.db.sql.call_args_list if "total_items = %s" in c.args[0]]
		assert len(beats) == 1
		assert not any("Queued" in c.args[0] for c in fake_frappe.db.sql.call_args_list)
		assert fake_frappe.delete_doc.call_count == 10


class TestRunningCount:
	def test_total_items_tracks_running_count_before_finish_scan(self):
		bulk_sources, ctx = _scan_ctx()
		fake_frappe = MagicMock()
		with patch.object(bulk_sources, "frappe", fake_frappe), patch.object(bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()):
			for i in range(30):
				ctx.add_content(f"k{i}", f"a{i}.txt", b"a")
		beats = [c for c in fake_frappe.db.sql.call_args_list if "total_items = %s" in c.args[0]]
		assert [c.args[1][0] for c in beats] == [10, 20, 30]
		assert all("status = 'Scanning'" in c.args[0] for c in beats)

		fake_frappe = MagicMock()
		fake_frappe.db.get_value.return_value = "Scanning"
		with patch.object(bulk_sources, "frappe", fake_frappe), patch.object(bulk_sources, "now_datetime", return_value=__import__("datetime").datetime(2026, 1, 1)):
			bulk_sources.finish_scan("ING-1", ctx.entries)
		assert fake_frappe.db.sql.call_args.args[1][0] == 30


class TestStaleScanningRecovery:
	def test_conditional_update(self):
		from huf.ai.knowledge import bulk_recovery

		fake_frappe = MagicMock()
		fake_frappe.get_all.side_effect = lambda dt, filters=None, pluck=None, **kw: ["ING-1"] if filters == {"status": "Scanning"} else []
		fake_frappe.db.get_value.return_value = __import__('datetime').datetime(2000, 1, 1)
		with patch.object(bulk_recovery, "frappe", fake_frappe), patch.object(bulk_recovery, "now_datetime", return_value=__import__("datetime").datetime(2026, 1, 1)):
			try:
				bulk_recovery.recover_stalled_ingestions()
			except Exception:  # noqa: BLE001 -- later sections may need a DB; only the SQL matters
				pass
		sqls = [c.args[0] for c in fake_frappe.db.sql.call_args_list]
		assert any("status = 'Scanning' AND modified < %s" in q and "SET status = 'Failed'" in q for q in sqls)
		fake_frappe.db.set_value.assert_not_called()


class _Attr:
	def __init__(self, filename, mode, size=1):
		self.filename, self.st_mode, self.st_size = filename, mode, size


class TestSftpWalk:
	def test_walk_recurses_and_skips_links(self):
		from huf.ai.knowledge.sources.sftp_client import walk_sftp

		tree = {
			"/data": [_Attr("a.txt", stat.S_IFREG, 4), _Attr("sub", stat.S_IFDIR), _Attr("ln", stat.S_IFLNK), _Attr("..", stat.S_IFDIR)],
			"/data/sub": [_Attr("b.pdf", stat.S_IFREG, 9), _Attr("dev", stat.S_IFCHR)],
		}
		sftp = MagicMock()
		sftp.listdir_attr.side_effect = lambda p: tree[p]
		out = list(walk_sftp(sftp, "/data", 100))
		assert sorted((rel, size) for _f, rel, size in out) == [("a.txt", 4), ("sub/b.pdf", 9)]

	def test_walk_truncation_signal(self):
		from huf.ai.knowledge.sources.sftp_client import walk_sftp

		sftp = MagicMock()
		sftp.listdir_attr.return_value = [_Attr(f"{i}.txt", stat.S_IFREG) for i in range(10)]
		assert len(list(walk_sftp(sftp, "/d", 3))) == 4

	def test_normalize_root_rejects_traversal(self):
		from huf.ai.knowledge.sources.sftp_client import normalize_root

		assert normalize_root("data//x/") == "/data/x"
		with pytest.raises(ValueError):
			normalize_root("/data/../etc")
		with pytest.raises(ValueError):
			normalize_root("")

	def test_scan_sftp_entries_with_mocked_paramiko(self):
		bulk_sources, ctx = _scan_ctx()
		sftp = MagicMock()
		tree = {"/r": [_Attr("a.md", stat.S_IFREG, 3), _Attr("x.bin", stat.S_IFREG, 3), _Attr("big.txt", stat.S_IFREG, 99999)]}
		sftp.listdir_attr.side_effect = lambda p: tree[p]
		handle = MagicMock()
		handle.__enter__.return_value.read.return_value = b"# a"
		sftp.open.return_value = handle
		transport = MagicMock()
		with patch("huf.ai.knowledge.sources.sftp_client.open_sftp", return_value=(transport, sftp)), patch.object(
			bulk_sources, "make_private_file", side_effect=lambda *a: _fake_file()
		):
			bulk_sources.scan_sftp(ctx, {"ssh_connection": "conn1", "root_path": "/r"})
		by_key = {e["external_key"]: e for e in ctx.entries}
		assert by_key["sftp://conn1/r/a.md"]["file"]
		assert by_key["sftp://conn1/r/x.bin"]["skip_reason"] == "Unsupported"
		assert by_key["sftp://conn1/r/big.txt"]["skip_reason"] == "Too Large"
		transport.close.assert_called_once()


class _Throw(Exception):
	pass


class _PermErr(Exception):
	pass


@pytest.fixture
def api():
	"""bulk_sources_api with frappe mocked so throw() raises and whitelist is a no-op."""
	import frappe

	stubbed = isinstance(frappe.whitelist, MagicMock)
	if stubbed:
		frappe.whitelist = lambda *a, **k: (lambda f: f)
	import huf.ai.knowledge.bulk_sources_api as mod

	if stubbed:
		mod = importlib.reload(mod)
	fake = MagicMock()
	fake.PermissionError = _PermErr
	fake.throw.side_effect = lambda msg, exc=None: (_ for _ in ()).throw((exc or _Throw)(str(msg)))
	fake.conf = {"huf_bulk_directory_roots": []}
	fake.get_roles.return_value = ["Huf Manager"]
	fake.db.exists.return_value = True
	fake.has_permission.return_value = True
	with patch.object(mod, "frappe", fake):
		yield mod, fake


class TestStartImportValidation:
	def test_not_post_only(self):
		import inspect

		src = inspect.getsource(importlib.import_module("huf.ai.knowledge.bulk_sources_api"))
		assert '@frappe.whitelist(methods=["POST"])\ndef start_import' in src

	def test_write_permission_denied(self, api):
		mod, fake = api
		fake.has_permission.return_value = False
		with pytest.raises(_PermErr):
			mod.start_import("KS-1", "Zip", {"file": "F1"})
		fake.enqueue.assert_not_called()

	def test_directory_requires_system_manager(self, api, tmp_path):
		mod, fake = api
		fake.conf = {"huf_bulk_directory_roots": [str(tmp_path)]}
		with pytest.raises(_PermErr):
			mod.start_import("KS-1", "Directory", {"path": str(tmp_path)})

	def test_directory_outside_roots(self, api, tmp_path):
		mod, fake = api
		fake.conf = {"huf_bulk_directory_roots": [str(tmp_path / "ok")]}
		fake.get_roles.return_value = ["System Manager"]
		with pytest.raises(_PermErr):
			mod.start_import("KS-1", "Directory", {"path": "/etc"})

	def test_unknown_kind_and_bad_shapes(self, api):
		mod, _fake = api
		for kind, cfg in [("FTP", {}), ("Upload", {"files": []}), ("Zip", {}), ("S3", {"prefix": "x"}), ("SFTP", {"ssh_connection": "c"})]:
			with pytest.raises(_Throw):
				mod.start_import("KS-1", kind, cfg)

	def test_sftp_connection_permission(self, api):
		mod, fake = api
		fake.has_permission.side_effect = lambda dt, ptype, doc=None: dt != "SSH Connection"
		with pytest.raises(_PermErr):
			mod.start_import("KS-1", "SFTP", {"ssh_connection": "c1", "root_path": "/r"})

	def test_active_ingestion_blocks(self, api):
		mod, fake = api
		fake.db.exists.side_effect = lambda dt, *a: "ING-9" if dt == "Knowledge Ingestion" else True
		with pytest.raises(_Throw):
			mod.start_import("KS-1", "S3", {"bucket": "b"})

	def test_happy_path_acks_scanning_and_enqueues(self, api):
		mod, fake = api
		fake.db.exists.side_effect = lambda dt, *a: False if dt == "Knowledge Ingestion" else True
		with patch.object(mod, "create_ingestion_header", return_value=types.SimpleNamespace(name="ING-5")) as hdr:
			out = mod.start_import("KS-1", "S3", '{"bucket": "b", "prefix": "p/"}')
		assert out == {"ingestion": "ING-5", "status": "Scanning", "source_kind": "S3"}
		assert hdr.call_args.kwargs["status"] == "Scanning" and hdr.call_args.kwargs["source_kind"] == "S3"
		kwargs = fake.enqueue.call_args.kwargs
		assert kwargs["queue"] == "long" and kwargs["config"] == {"bucket": "b", "prefix": "p/"}


class TestMaterializeUnsafeEntry:
	"""materialize() routes Unsafe zip members (no File) through the preset-skip path."""

	ENTRY = {"external_key": "zip://F/../evil.txt", "file": None, "checksum": None, "skip_reason": "Unsafe"}

	def _fake_frappe(self):
		rows = {}  # name -> row dict
		inserted = []

		def get_value(doctype, filters, fieldname=None, *a, **kw):
			if doctype == "Knowledge Ingestion":
				return "KS-1"
			assert doctype == "Knowledge Input"
			if isinstance(filters, dict):
				for name, row in rows.items():
					if row["external_key"] == filters.get("external_key"):
						return name
				return None
			return rows[filters][fieldname]

		def set_value(doctype, name, values):
			rows[name].update(values)

		def get_doc(data):
			doc = MagicMock()
			doc.flags = types.SimpleNamespace()
			doc.data = data

			def insert(**kw):
				rows[f"KI-{len(rows) + 1}"] = dict(data)
				inserted.append(doc)

			doc.insert.side_effect = insert
			return doc

		fake = MagicMock()
		fake.flags = types.SimpleNamespace()
		fake.db.get_value.side_effect = get_value
		fake.db.set_value.side_effect = set_value
		fake.get_doc.side_effect = get_doc
		return fake, rows, inserted

	def test_unsafe_inserted_skipped_then_updated_not_duplicated(self):
		from huf.ai.knowledge import bulk_materialize as bm

		fake, rows, inserted = self._fake_frappe()
		with patch.object(bm, "frappe", fake):
			stats = bm.materialize("ING-1", [dict(self.ENTRY)])
			assert len(inserted) == 1 and len(rows) == 1
			doc = inserted[0]
			assert doc.data["status"] == "Skipped"
			assert doc.data["skip_reason"] == "Unsafe"
			assert doc.flags.ignore_validate is True
			assert stats["skipped_preset"] == 1

			bm.materialize("ING-2", [dict(self.ENTRY)])
		assert len(inserted) == 1 and len(rows) == 1
		row = next(iter(rows.values()))
		assert row["status"] == "Skipped" and row["skip_reason"] == "Unsafe"
		assert row["ingestion"] == "ING-2"
