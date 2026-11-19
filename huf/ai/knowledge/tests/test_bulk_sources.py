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
	return bulk_sources, ctx


def _fake_file(counter=[0]):
	counter[0] += 1
	return types.SimpleNamespace(name=f"F{counter[0]}", file_url=f"/private/files/f{counter[0]}")


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
