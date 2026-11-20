# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Bulk ingestion source scanners.

Every source (Upload, Zip, Directory, S3, SFTP) is scanned in a background
job (``run_scan``) that produces private File docs and a manifest of
``{"file", "file_url", "external_key", "checksum"}`` entries (plus
``skip_reason`` entries for files that are Too Large / Unsupported and get no
File). ``finish_scan`` then moves the header Scanning -> Queued and enqueues
the existing ``run_ingestion`` through ``bulk_api.enqueue_first_slice``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time

import frappe
from frappe import _
from frappe.utils import now_datetime

from ..bulk_api import enqueue_first_slice
from ..bulk_runner import serialize_manifest
from .safety import (
	SourceSafetyError,
	classify,
	expand_zip,
	load_limits,
	resolve_under_roots,
	walk_directory,
)

HEARTBEAT_EVERY = 10
HEARTBEAT_WRITE_INTERVAL = 2  # seconds: also write at least this often, besides every N files
HEARTBEAT_MIN_INTERVAL = 30  # seconds, for forced/throttled heartbeats
MAX_KEY_LEN = 255


def make_external_key(raw: str) -> str:
	"""Fit ``raw`` into the 255-char external_key column deterministically.

	Long keys become first 190 chars + "#" + sha1(full key) so distinct long
	keys never collide and re-imports map to the same row."""
	raw = raw or ""
	if len(raw) <= MAX_KEY_LEN:
		return raw
	return raw[:190] + "#" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ScanCancelled(Exception):
	"""Raised from a heartbeat when the header is no longer Scanning (cancelled)."""


class ScanContext:
	"""Per-scan state: limits, manifest accumulation, header heartbeat."""

	def __init__(self, ingestion_name: str, knowledge_source: str, limits):
		self.ingestion_name = ingestion_name
		self.knowledge_source = knowledge_source
		self.limits = limits
		self.entries: list = []
		self.truncated = False
		self._seen = 0
		self.created_files: list = []
		self._last_beat = 0.0
		self._last_write = time.monotonic()

	@property
	def full(self) -> bool:
		return len(self.entries) >= self.limits.max_files

	def add_skip(self, key: str, reason: str) -> None:
		if self.full:
			self.truncated = True
			return
		self.entries.append(
			{"file": None, "file_url": None, "external_key": make_external_key(key), "checksum": None, "skip_reason": reason}
		)
		self.touch()

	def add_content(self, key: str, filename: str, content: bytes) -> None:
		if self.full:
			self.truncated = True
			return
		if not content:
			# A zero-byte file cannot become a File doc (Frappe rejects it with
			# "File does not exist"); record it as skipped instead of failing the scan.
			return self.add_skip(key, "No Text")
		file_doc = make_private_file(self.knowledge_source, filename, content)
		self.created_files.append(file_doc.name)
		self.entries.append(
			{
				"file": file_doc.name,
				"file_url": file_doc.file_url,
				"external_key": make_external_key(key),
				"checksum": hashlib.sha256(content).hexdigest(),
			}
		)
		self.heartbeat()

	def add_local(self, key: str, filename: str, path: str, size: int) -> None:
		reason = classify(filename, size, self.limits)
		if reason:
			return self.add_skip(key, reason)
		with open(path, "rb") as handle:
			self.add_content(key, filename, handle.read())

	def touch(self, force: bool = False) -> None:
		"""Bump the header's ``modified`` (throttled to once per interval unless forced)."""
		now = time.monotonic()
		if not force and self._last_beat and now - self._last_beat < HEARTBEAT_MIN_INTERVAL:
			return
		self._last_beat = now
		self._beat()

	def _beat(self) -> None:
		"""Publish the running count + bump ``modified`` while the header is still Scanning.

		Conditional on ``status = 'Scanning'`` so a cancel is never overwritten; if no row
		matches the header was cancelled, so stop the walk (``run_scan`` cleans up)."""
		frappe.db.sql(
			"UPDATE `tabKnowledge Ingestion` SET total_items = %s, modified = %s WHERE name = %s AND status = 'Scanning'",
			(len(self.entries), now_datetime(), self.ingestion_name),
		)
		affected = frappe.db._cursor.rowcount
		frappe.db.commit()
		self._last_write = time.monotonic()
		if affected == 0:
			raise ScanCancelled(self.ingestion_name)

	def zip_progress(self) -> None:
		self.touch()

	def cleanup_created_files(self) -> None:
		"""Delete File docs this scan created (never user-uploaded ones it only referenced)."""
		for name in self.created_files:
			try:
				frappe.delete_doc("File", name, ignore_permissions=True, force=True)
			except Exception:  # noqa: BLE001 -- best effort
				pass
		self.created_files = []
		frappe.db.commit()

	def heartbeat(self) -> None:
		self._seen += 1
		due = time.monotonic() - self._last_write >= HEARTBEAT_WRITE_INTERVAL
		if self._seen % HEARTBEAT_EVERY == 0 or due:
			self._beat()


def make_private_file(knowledge_source: str, filename: str, content: bytes):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": os.path.basename(filename)[:140] or "file",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "Knowledge Source",
			"attached_to_name": knowledge_source,
		}
	).insert(ignore_permissions=True)


def _add_expanded(ctx: ScanContext, result) -> None:
	for item in result.files:
		if item.skip_reason:
			ctx.add_skip(item.rel, item.skip_reason)
		else:
			ctx.add_local(item.rel, item.rel, item.path, item.size)
	# Blocked members (zip-slip, symlink, encrypted, too deep) are never
	# extracted; surface them as Skipped/Unsafe. The name is stored only as text
	# in external_key (truncated by make_external_key), never used as a path.
	for member, _reason in getattr(result, "blocked", None) or []:
		ctx.add_skip(member, "Unsafe")


# --- Scanners (each fills ctx.entries) -------------------------------------

def scan_upload(ctx: ScanContext, config: dict) -> None:
	for ref in config.get("files") or []:
		file_doc = frappe.get_doc("File", ref)
		if not frappe.has_permission("File", "read", doc=file_doc):
			continue
		scan_file_doc(ctx, file_doc)


def scan_zip(ctx: ScanContext, config: dict) -> None:
	file_doc = frappe.get_doc("File", config.get("file"))
	if not frappe.has_permission("File", "read", doc=file_doc):
		frappe.throw(_("Not permitted to read the zip file"), frappe.PermissionError)
	scan_file_doc(ctx, file_doc, force_zip=True)


def scan_file_doc(ctx: ScanContext, file_doc, force_zip: bool = False) -> None:
	name = file_doc.file_name or file_doc.name
	upload_key = f"upload://{file_doc.name}"
	if name.lower().endswith(".zip") or force_zip:
		tmp = tempfile.mkdtemp(prefix="huf_zip_")
		try:
			zip_path = os.path.join(tmp, "in.zip")
			content = file_doc.get_content()
			with open(zip_path, "wb") as handle:
				handle.write(content.encode() if isinstance(content, str) else content)
			_add_expanded(ctx, expand_zip(zip_path, os.path.join(tmp, "out"), ctx.limits, prefix=f"zip://{file_doc.name}/", on_progress=ctx.zip_progress))
		finally:
			shutil.rmtree(tmp, ignore_errors=True)
		return
	reason = classify(name, file_doc.file_size, ctx.limits)
	if reason:
		return ctx.add_skip(upload_key, reason)
	if file_doc.is_private:
		if ctx.full:
			ctx.truncated = True
			return
		content = file_doc.get_content()
		content = content.encode() if isinstance(content, str) else content
		ctx.entries.append(
			{
				"file": file_doc.name,
				"file_url": file_doc.file_url,
				"external_key": make_external_key(upload_key),
				"checksum": hashlib.sha256(content).hexdigest(),
			}
		)
		return
	content = file_doc.get_content()
	ctx.add_content(upload_key, name, content.encode() if isinstance(content, str) else content)


def scan_directory(ctx: ScanContext, config: dict) -> None:
	root = resolve_under_roots(config.get("path"), frappe.conf.get("huf_bulk_directory_roots") or [])
	for rel, full, size in walk_directory(root, ctx.limits):
		ctx.add_local(rel, rel, full, size)


def scan_s3(ctx: ScanContext, config: dict) -> None:
	# Lazy: huf/ai/tools/s3.py is owned by the S3 track.
	from huf.ai.tools.s3 import download_object, get_s3_client, list_objects_page

	bucket, prefix = config["bucket"], config.get("prefix") or ""
	client = get_s3_client(config.get("credential"))
	token = None
	while True:
		page = list_objects_page(client, bucket, prefix=prefix, continuation_token=token, page_size=1000)
		ctx.touch(force=True)
		for obj in page.get("objects") or []:
			key, size = obj["key"], int(obj.get("size") or 0)
			ext_key = f"s3://{bucket}/{key}"
			reason = classify(key, size, ctx.limits)
			if reason:
				ctx.add_skip(ext_key, reason)
			elif ctx.full:
				ctx.truncated = True
			else:
				ctx.add_content(ext_key, key, download_object(client, bucket, key, ctx.limits.max_file_bytes))
		token = page.get("next_token")
		if not token or ctx.truncated:
			break


def scan_sftp(ctx: ScanContext, config: dict) -> None:
	from .sftp_client import normalize_root, open_sftp, read_remote, walk_sftp

	conn = config["ssh_connection"]
	root = normalize_root(config["root_path"])
	transport, sftp = open_sftp(conn)
	try:
		for remote, rel, size in walk_sftp(sftp, root, ctx.limits.max_files, on_dir=lambda: ctx.touch(force=True)):
			ext_key = f"sftp://{conn}{remote}"
			reason = classify(rel, size, ctx.limits)
			if reason:
				ctx.add_skip(ext_key, reason)
			elif ctx.full:
				ctx.truncated = True
				break
			else:
				ctx.add_content(ext_key, rel, read_remote(sftp, remote, ctx.limits.max_file_bytes))
	finally:
		transport.close()


SCANNERS = {
	"Upload": scan_upload,
	"Zip": scan_zip,
	"Directory": scan_directory,
	"S3": scan_s3,
	"SFTP": scan_sftp,
}


# --- Background job --------------------------------------------------------

def run_scan(ingestion_name: str, source_kind: str, config: dict) -> dict:
	"""Background job: scan the source, then hand the manifest to the runner."""
	frappe.flags.huf_bulk_ingestion = True
	source = frappe.db.get_value("Knowledge Ingestion", ingestion_name, "knowledge_source")
	ctx = ScanContext(ingestion_name, source, load_limits(frappe.conf))
	try:
		SCANNERS[source_kind](ctx, config)
	except ScanCancelled:
		frappe.db.rollback()
		ctx.cleanup_created_files()
		return {"status": "cancelled"}
	except Exception as exc:  # noqa: BLE001 -- any scan failure fails the header, not the worker
		frappe.db.rollback()
		ctx.cleanup_created_files()
		_fail_scan(ingestion_name, str(exc))
		return {"status": "failed", "error": str(exc)[:500]}
	return finish_scan(ingestion_name, ctx.entries, ctx.truncated, created_files=ctx.created_files)


def _fail_scan(ingestion_name: str, message: str) -> None:
	frappe.db.sql(
		"UPDATE `tabKnowledge Ingestion` SET status = 'Failed', finished_at = %s, error_message = %s, modified = %s "
		"WHERE name = %s AND status = 'Scanning'",
		(now_datetime(), message[:500], now_datetime(), ingestion_name),
	)
	frappe.db.commit()


def _delete_files(names) -> None:
	for name in names or []:
		try:
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)
		except Exception:  # noqa: BLE001 -- best effort
			pass
	frappe.db.commit()


def finish_scan(ingestion_name: str, entries: list, truncated: bool = False, created_files: list | None = None) -> dict:
	"""Scanning -> Queued with the manifest, then enqueue the shared runner."""
	if not entries:
		_delete_files(created_files)
		_fail_scan(ingestion_name, "No files found at the source")
		return {"status": "failed", "error": "No files found at the source"}
	updates = {"total_items": len(entries), "manifest_json": serialize_manifest(entries)}
	if truncated:
		updates["error_message"] = _("Source had more files than the limit; only the first {0} were imported").format(len(entries))
	# Conditional on Scanning so a cancel during the scan wins.
	frappe.db.sql(
		"UPDATE `tabKnowledge Ingestion` SET status = 'Queued', total_items = %s, manifest_json = %s, "
		"error_message = %s, modified = %s WHERE name = %s AND status = 'Scanning'",
		(updates["total_items"], updates["manifest_json"], updates.get("error_message"), now_datetime(), ingestion_name),
	)
	frappe.db.commit()
	if frappe.db.get_value("Knowledge Ingestion", ingestion_name, "status") != "Queued":
		_delete_files(created_files)
		return {"status": "cancelled"}
	enqueue_first_slice(ingestion_name, entries)
	return {"status": "queued", "total_items": len(entries)}
