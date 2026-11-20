# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Whitelisted API for starting bulk imports from Upload / Zip / Directory /
S3 / SFTP sources. Validates + permission-checks, creates the Scanning header,
and acks; the scan runs in ``sources.scanners.run_scan`` (queue long)."""

from __future__ import annotations

import json
import os

import frappe
from frappe import _

from .bulk_api import create_ingestion_header
from .bulk_runner import ACTIVE_INGESTION_STATUSES
from .sources.safety import load_limits, resolve_under_roots

SOURCE_KINDS = ("Upload", "Zip", "Directory", "S3", "SFTP")
SCAN_TIMEOUT = 3600


def _deny(message: str):
	frappe.throw(message, frappe.PermissionError)


def parse_config(config) -> dict:
	if isinstance(config, str):
		try:
			config = json.loads(config)
		except ValueError:
			frappe.throw(_("config must be a JSON object"))
	if not isinstance(config, dict):
		frappe.throw(_("config must be a JSON object"))
	return config


def validate_config(source_kind: str, config: dict, roots=None) -> dict:
	"""Shape validation per kind; returns a normalized, non-secret config echo.

	Raises frappe.ValidationError for bad shape and PermissionError for a
	Directory path outside the allowed roots. Pure given ``roots``.
	"""
	if source_kind not in SOURCE_KINDS:
		frappe.throw(_("Unknown source_kind {0}").format(source_kind))
	if source_kind == "Upload":
		files = config.get("files")
		if not isinstance(files, list) or not files or not all(isinstance(f, str) and f for f in files):
			frappe.throw(_("config.files must be a non-empty list of File names"))
		return {"files": files}
	if source_kind == "Zip":
		if not isinstance(config.get("file"), str) or not config["file"]:
			frappe.throw(_("config.file (a File name) is required"))
		return {"file": config["file"]}
	if source_kind == "Directory":
		try:
			real = resolve_under_roots(config.get("path"), roots)
		except PermissionError as exc:
			_deny(str(exc))
		if not os.path.isdir(real):
			frappe.throw(_("Directory does not exist"))
		return {"path": real}
	if source_kind == "S3":
		bucket = config.get("bucket")
		if not isinstance(bucket, str) or not bucket.strip():
			frappe.throw(_("config.bucket is required"))
		return {"bucket": bucket.strip(), "prefix": str(config.get("prefix") or "")}
	conn, root = config.get("ssh_connection"), config.get("root_path")
	if not isinstance(conn, str) or not conn or not isinstance(root, str) or not root.strip():
		frappe.throw(_("config.ssh_connection and config.root_path are required"))
	from huf.ai.knowledge.sources.sftp_client import normalize_root

	try:
		root = normalize_root(root)
	except ValueError as e:
		frappe.throw(str(e))
	return {"ssh_connection": conn, "root_path": root}


def _check_base_permissions(knowledge_source: str, source_kind: str) -> None:
	if not frappe.db.exists("Knowledge Source", knowledge_source):
		frappe.throw(_("Knowledge Source {0} does not exist").format(knowledge_source))
	if not frappe.has_permission("Knowledge Source", "write", doc=knowledge_source):
		_deny(_("Not permitted to write to Knowledge Source {0}").format(knowledge_source))
	if source_kind == "Directory" and "System Manager" not in frappe.get_roles():
		_deny(_("Only a System Manager can import from a server directory"))


def _check_ref_permissions(source_kind: str, config: dict) -> None:
	if source_kind == "SFTP":
		if not frappe.has_permission("SSH Connection", "read", doc=config["ssh_connection"]):
			_deny(_("Not permitted to use SSH Connection {0}").format(config["ssh_connection"]))
	if source_kind in ("Upload", "Zip"):
		for ref in config.get("files") or [config.get("file")]:
			if not frappe.db.exists("File", ref):
				frappe.throw(_("File {0} does not exist").format(ref))
			if not frappe.has_permission("File", "read", doc=ref):
				_deny(_("Not permitted to read File {0}").format(ref))


@frappe.whitelist(methods=["POST"])
def start_import(knowledge_source: str, source_kind: str, config):
	"""Start a bulk import; returns ``{"ingestion", "status": "Scanning", "source_kind"}``."""
	config = parse_config(config)
	roots = frappe.conf.get("huf_bulk_directory_roots") or []
	# Permission first (cheap, no side effects), then shape validation, then
	# per-reference (File / SSH Connection) permissions.
	_check_base_permissions(knowledge_source, source_kind)
	normalized = validate_config(source_kind, config, roots)
	_check_ref_permissions(source_kind, normalized)

	existing = frappe.db.exists(
		"Knowledge Ingestion",
		{"knowledge_source": knowledge_source, "status": ("in", ACTIVE_INGESTION_STATUSES)},
	)
	if existing:
		frappe.throw(_("An ingestion ({0}) is already queued or running for this source").format(existing))

	echo = {k: v for k, v in normalized.items() if k != "files"} if source_kind != "Upload" else {"files": len(normalized["files"])}
	ingestion = create_ingestion_header(
		knowledge_source, status="Scanning", source_kind=source_kind, source_config=echo
	)
	from .sources.scanners import run_scan

	frappe.enqueue(
		run_scan,
		queue="long",
		timeout=SCAN_TIMEOUT,
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=f"huf_scan_{ingestion.name}",
		ingestion_name=ingestion.name,
		source_kind=source_kind,
		config=normalized,
	)
	return {"ingestion": ingestion.name, "status": "Scanning", "source_kind": source_kind}


@frappe.whitelist()
def get_import_options(knowledge_source: str):
	"""Which source kinds are usable here, plus pickers' data. Read-only."""
	if not frappe.has_permission("Knowledge Source", "read", doc=knowledge_source):
		_deny(_("Not permitted to read Knowledge Source {0}").format(knowledge_source))
	limits = load_limits(frappe.conf)
	is_admin = "System Manager" in frappe.get_roles()
	roots = list(frappe.conf.get("huf_bulk_directory_roots") or []) if is_admin else []
	ssh = [
		{"name": r.name, "label": r.display_name or r.name}
		for r in frappe.get_list(
			"SSH Connection", filters={"enabled": 1}, fields=["name", "display_name"], limit_page_length=100
		)
	]
	s3_configured = bool(
		frappe.db.exists("Integration Settings", {"service": "S3", "is_active": 1})
		or os.getenv("S3_ACCESS_KEY_ID")
	)
	kinds = ["Upload", "Zip"]
	if roots:
		kinds.append("Directory")
	if s3_configured:
		kinds.append("S3")
	if ssh:
		kinds.append("SFTP")
	return {
		"source_kinds": kinds,
		"directory_roots": roots,
		"ssh_connections": ssh,
		"s3_configured": s3_configured,
		"max_files": limits.max_files,
		"max_file_mb": limits.max_file_bytes // (1024 * 1024),
		"allowed_extensions": list(limits.extensions),
	}
