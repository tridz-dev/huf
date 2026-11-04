"""SFTP-based bulk-source client for Ingestion Job scanning.

Distinct from ``huf.ai.tools.ssh_execution``, which is a one-shot
command-execution tool with a human-approval workflow and a capped
output size -- the wrong fit for bulk file listing/transfer. This
module opens a dedicated paramiko SFTP channel instead, reusing the
same private-key loading and strict pinned host-key verification
logic as ``ssh_execution.py`` so authentication and host-key pinning
behavior stay identical across both tools.
"""

from __future__ import annotations

import stat

import frappe
import paramiko

from huf.ai.tools.ssh_execution import _fingerprint_for_key, _load_private_key

DEFAULT_PAGE_LIMIT = 200


class _PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
	"""Accept the server key only if it matches the SSH Connection's pinned fingerprint."""

	def __init__(self, connection_doc):
		self.connection_doc = connection_doc

	def missing_host_key(self, client, hostname, key):
		fingerprint = _fingerprint_for_key(key)
		expected = (self.connection_doc.host_key_fingerprint or "").strip()
		if fingerprint != expected:
			frappe.throw(
				f"SSH host key mismatch for {self.connection_doc.name}. Expected {expected}, got {fingerprint}.",
				frappe.ValidationError,
			)
		if (self.connection_doc.host_key_type or "").strip() and key.get_name() != self.connection_doc.host_key_type:
			frappe.throw(
				f"SSH host key type mismatch for {self.connection_doc.name}. "
				f"Expected {self.connection_doc.host_key_type}, got {key.get_name()}.",
				frappe.ValidationError,
			)


def _connect(ssh_connection_name: str):
	"""Authenticate to the SSH Connection and open an SFTP channel.

	Reuses the same key-loading and password/private-key branching as
	``ssh_execution.py``, and enforces the same strict pinned host-key
	verification when ``host_key_verification`` is "Strict (Pinned)".
	Returns (ssh_client, sftp_client) -- the caller closes both when done.
	"""
	connection_doc = frappe.get_doc("SSH Connection", ssh_connection_name)

	if connection_doc.host_key_verification == "Strict (Pinned)" and not (
		connection_doc.host_key_fingerprint or ""
	).strip():
		frappe.throw(
			f"SSH Connection '{connection_doc.name}' requires strict pinned host-key verification "
			"but has no enrolled host key fingerprint.",
			frappe.ValidationError,
		)

	ssh_client = paramiko.SSHClient()
	if connection_doc.host_key_verification == "Strict (Pinned)":
		ssh_client.set_missing_host_key_policy(_PinnedHostKeyPolicy(connection_doc))
	else:
		ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

	connect_kwargs = {
		"hostname": connection_doc.host,
		"port": int(connection_doc.port or 22),
		"username": connection_doc.username,
	}

	if connection_doc.auth_method == "Password":
		connect_kwargs["password"] = connection_doc.get_password("password")
	else:
		pkey = _load_private_key(
			connection_doc.get_password("private_key"),
			connection_doc.get_password("private_key_passphrase", raise_exception=False),
		)
		connect_kwargs["pkey"] = pkey

	ssh_client.connect(**connect_kwargs)

	sftp_client = ssh_client.open_sftp()
	return ssh_client, sftp_client


def list_dir_recursive(sftp, dir_queue, page_limit=DEFAULT_PAGE_LIMIT):
	"""Pop directories off the front of `dir_queue`, listing files and enqueueing subdirectories.

	`dir_queue` is a plain list of remote directory path strings acting as a
	resumable cursor. Directories are popped from the front and visited one
	at a time; any subdirectories discovered are appended to the end of
	`dir_queue` so a crashed/paused scan can resume from the same frontier.
	Stops once `page_limit` files have been collected or `dir_queue` is empty.
	Returns (files_collected, remaining_dir_queue).
	"""
	files_collected = []

	while dir_queue and len(files_collected) < page_limit:
		current_dir = dir_queue.pop(0)

		for entry in sftp.listdir_attr(current_dir):
			full_path = f"{current_dir.rstrip('/')}/{entry.filename}"

			if stat.S_ISDIR(entry.st_mode):
				dir_queue.append(full_path)
			else:
				files_collected.append(
					{
						"path": full_path,
						"size": entry.st_size,
						"mtime": entry.st_mtime,
					}
				)

				if len(files_collected) >= page_limit:
					break

	return files_collected, dir_queue


def read_file(sftp, remote_path, local_tmp_path):
	"""Stream `remote_path` down to `local_tmp_path` via SFTP. Returns `local_tmp_path`."""
	sftp.get(remote_path, local_tmp_path)
	return local_tmp_path
