# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""SFTP access for bulk ingestion, reusing the SSH Connection doctype and the
pinned-host-key transport from huf.ai.tools.ssh_execution."""

from __future__ import annotations

import posixpath
import stat

import frappe
from frappe import _

MAX_WALK_DEPTH = 20


def open_sftp(connection_name: str):
	"""Return ``(transport, sftp)`` for an enabled, host-key-enrolled SSH Connection."""
	import paramiko

	from huf.ai.tools.ssh_execution import _connect_transport

	connection_doc = frappe.get_doc("SSH Connection", connection_name)
	if not getattr(connection_doc, "enabled", None):
		frappe.throw(_("The selected SSH connection is disabled."))
	if not (connection_doc.host_key_fingerprint or "").strip():
		frappe.throw(_("The selected SSH connection has no enrolled host key fingerprint."))
	transport, _fingerprint, _key_type = _connect_transport(connection_doc, {})
	try:
		return transport, paramiko.SFTPClient.from_transport(transport)
	except Exception:
		transport.close()
		raise


def normalize_root(root_path: str) -> str:
	"""Absolute POSIX root without ``..`` segments (remote side is jailed by the
	server account; this just rejects traversal tricks in the config)."""
	root = (root_path or "").strip()
	if not root or "\0" in root or ".." in root.replace("\\", "/").split("/"):
		raise ValueError("root_path must be a path without '..'")
	return posixpath.normpath(root if root.startswith("/") else "/" + root)


def walk_sftp(sftp, root: str, max_files: int):
	"""Yield ``(remote_path, rel_path, size)`` for regular files under ``root``.

	Symlinks and special files are skipped. Yields at most ``max_files + 1``
	entries (the extra one signals truncation) and recurses to MAX_WALK_DEPTH.
	"""
	count = 0
	stack = [(root, 0)]
	while stack:
		current, depth = stack.pop()
		try:
			entries = sftp.listdir_attr(current)
		except OSError:
			continue
		for attr in sorted(entries, key=lambda a: a.filename):
			name = attr.filename
			if name in (".", "..") or "/" in name:
				continue
			mode = attr.st_mode or 0
			full = posixpath.join(current, name)
			if stat.S_ISLNK(mode):
				continue
			if stat.S_ISDIR(mode):
				if depth < MAX_WALK_DEPTH:
					stack.append((full, depth + 1))
				continue
			if not stat.S_ISREG(mode):
				continue
			yield full, posixpath.relpath(full, root), int(attr.st_size or 0)
			count += 1
			if count > max_files:
				return


def read_remote(sftp, remote_path: str, max_bytes: int) -> bytes:
	"""Read a remote file, refusing more than ``max_bytes`` (size can change after stat)."""
	with sftp.open(remote_path, "rb") as handle:
		data = handle.read(max_bytes + 1)
	if len(data) > max_bytes:
		raise ValueError("Remote file exceeds the size limit")
	return data
