# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

import base64
import hashlib
import io
import socket

import paramiko


_PASSWORD_FIELDS = ("password", "private_key", "private_key_passphrase")


class SSHConnection(Document):
	def validate(self):
		self._preserve_existing_blank_passwords()
		self._validate_auth_fields()
		self._validate_host_fields()

	def has_permission(self, permission_type=None, verbose=False):
		from huf.permissions import has_capability

		user = frappe.session.user
		if "System Manager" in frappe.get_roles(user):
			return True

		if permission_type in ("create", "write", "save", "delete"):
			return has_capability(user, "ssh_connection.manage")

		return True

	def _preserve_existing_blank_passwords(self):
		if self.is_new():
			return

		ignored = list(getattr(self.flags, "ignore_save_passwords", []) or [])
		for fieldname in _PASSWORD_FIELDS:
			if self.get(fieldname):
				continue
			if self.get_password(fieldname, raise_exception=False):
				ignored.append(fieldname)

		if ignored:
			self.flags.ignore_save_passwords = list(dict.fromkeys(ignored))

	def _validate_auth_fields(self):
		if self.auth_method == "Password":
			if not (self.password or self.get_password("password", raise_exception=False)):
				frappe.throw(_("Password is required for Password auth."), frappe.ValidationError)
			return

		if self.auth_method == "Private Key":
			if not (self.private_key or self.get_password("private_key", raise_exception=False)):
				frappe.throw(_("Private Key is required for Private Key auth."), frappe.ValidationError)
			return

		frappe.throw(_("Unsupported auth method: {0}").format(self.auth_method), frappe.ValidationError)

	def _validate_host_fields(self):
		if self.port is not None and int(self.port) <= 0:
			frappe.throw(_("Port must be a positive integer."), frappe.ValidationError)


def _require_manage_permission(doc: SSHConnection) -> None:
	if not doc.has_permission("write"):
		frappe.throw(_("You do not have permission to manage this SSH connection."), frappe.PermissionError)


def _fingerprint_for_key(server_key) -> str:
	digest = hashlib.sha256(server_key.asbytes()).digest()
	return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _load_private_key(doc: SSHConnection):
	private_key = doc.get_password("private_key")
	passphrase = doc.get_password("private_key_passphrase", raise_exception=False) or None
	for key_cls in (
		paramiko.Ed25519Key,
		paramiko.RSAKey,
		paramiko.ECDSAKey,
		paramiko.DSSKey,
	):
		try:
			return key_cls.from_private_key(io.StringIO(private_key), password=passphrase)
		except Exception:
			continue
	frappe.throw(_("Unsupported or invalid private key."), frappe.ValidationError)


def _open_transport(doc: SSHConnection) -> tuple[paramiko.Transport, str, str]:
	timeout = 10
	sock = socket.create_connection((doc.host, int(doc.port or 22)), timeout=timeout)
	transport = paramiko.Transport(sock)
	transport.banner_timeout = timeout
	transport.handshake_timeout = timeout
	transport.auth_timeout = timeout
	transport.start_client(timeout=timeout)
	server_key = transport.get_remote_server_key()
	fingerprint = _fingerprint_for_key(server_key)
	host_key_type = server_key.get_name()

	if doc.auth_method == "Password":
		transport.auth_password(
			username=doc.username,
			password=doc.get_password("password"),
		)
	else:
		transport.auth_publickey(username=doc.username, key=_load_private_key(doc))

	if not transport.is_authenticated():
		transport.close()
		frappe.throw(_("SSH authentication failed."), frappe.PermissionError)

	return transport, fingerprint, host_key_type


def _update_test_status(doc: SSHConnection, *, success: bool, error: str | None = None) -> None:
	doc.db_set("last_tested_on", now_datetime(), update_modified=False)
	doc.db_set("last_test_status", "Success" if success else "Failed", update_modified=False)
	doc.db_set("last_error", (error or "")[:140], update_modified=False)


@frappe.whitelist()
def test_ssh_connection(connection_name: str) -> dict:
	doc = frappe.get_doc("SSH Connection", connection_name)
	_require_manage_permission(doc)

	transport = None
	try:
		transport, fingerprint, host_key_type = _open_transport(doc)
		if doc.host_key_fingerprint and doc.host_key_fingerprint != fingerprint:
			message = _(
				"Host key mismatch. Expected {0}, got {1}."
			).format(doc.host_key_fingerprint, fingerprint)
			_update_test_status(doc, success=False, error=message)
			return {
				"success": False,
				"error": message,
				"fingerprint": fingerprint,
				"host_key_type": host_key_type,
			}

		_update_test_status(doc, success=True)
		return {
			"success": True,
			"fingerprint": fingerprint,
			"host_key_type": host_key_type,
			"host_key_enrolled": bool(doc.host_key_fingerprint),
		}
	except Exception as exc:  # noqa: BLE001
		_update_test_status(doc, success=False, error=str(exc))
		return {"success": False, "error": str(exc)}
	finally:
		if transport is not None:
			try:
				transport.close()
			except Exception:
				pass


@frappe.whitelist()
def enroll_host_key(connection_name: str) -> dict:
	doc = frappe.get_doc("SSH Connection", connection_name)
	_require_manage_permission(doc)

	transport = None
	try:
		transport, fingerprint, host_key_type = _open_transport(doc)
		doc.db_set("host_key_fingerprint", fingerprint, update_modified=False)
		doc.db_set("host_key_type", host_key_type, update_modified=False)
		doc.db_set("host_key_enrolled_by", frappe.session.user, update_modified=False)
		doc.db_set("host_key_enrolled_on", now_datetime(), update_modified=False)
		_update_test_status(doc, success=True)
		return {
			"success": True,
			"fingerprint": fingerprint,
			"host_key_type": host_key_type,
		}
	except Exception as exc:  # noqa: BLE001
		_update_test_status(doc, success=False, error=str(exc))
		return {"success": False, "error": str(exc)}
	finally:
		if transport is not None:
			try:
				transport.close()
			except Exception:
				pass


@frappe.whitelist()
def rotate_ssh_secret(
	connection_name: str,
	auth_method: str,
	password: str | None = None,
	private_key: str | None = None,
	private_key_passphrase: str | None = None,
) -> dict:
	doc = frappe.get_doc("SSH Connection", connection_name)
	_require_manage_permission(doc)

	doc.auth_method = auth_method
	if auth_method == "Password":
		doc.password = password or ""
		doc.private_key = ""
		doc.private_key_passphrase = ""
	else:
		doc.private_key = private_key or ""
		doc.private_key_passphrase = private_key_passphrase or ""
		doc.password = ""

	doc.key_rotated_on = now_datetime()
	doc.save(ignore_permissions=True)
	return {"success": True, "name": doc.name, "auth_method": doc.auth_method}
