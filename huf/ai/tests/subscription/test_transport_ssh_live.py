"""Live integration test for SSHExecTransport against a real sshd.

Unlike test_transport_ssh.py (fully mocked Paramiko), this test exercises the
actual SSHExecTransport / ssh_connection_primitive code against a real SSH
server, to prove strict host-key pinning and the exec/SFTP round trip work
end to end and not just against mocks.

Requires a real container reachable at 127.0.0.1:2222 running sshd with
user `tester` / password `tester` (see the `subcli-ssh-target` dev fixture
documented in Tracks/safwan-erooth.HufSubscriptionCLIProvider/LIVE_SSH_TRANSPORT_TEST.md).
Skipped automatically when that host/port is not reachable (e.g. in CI).

Since there is no live Frappe site available for these tests, the transport
is constructed by bypassing __init__ (which normally does frappe.get_doc)
and injecting a lightweight stand-in object exposing the same attributes an
'SSH Connection' Frappe doc would: host, port, username, auth_method,
host_key_fingerprint, host_key_type, get_password().
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import uuid

import pytest

paramiko = pytest.importorskip("paramiko")

from huf.ai.subscription.transports.ssh import SSHExecTransport
from huf.ai.tools.ssh_connection_primitive import fingerprint_for_key

HOST = "127.0.0.1"
PORT = 2222
USER = "tester"
PASSWORD = "tester"


def _host_reachable() -> bool:
	try:
		with socket.create_connection((HOST, PORT), timeout=2):
			return True
	except OSError:
		return False


pytestmark = pytest.mark.skipif(
	not _host_reachable(),
	reason=f"live SSH test target not reachable at {HOST}:{PORT}",
)


class StandInSSHConnection:
	"""Minimal stand-in for the 'SSH Connection' Frappe doc."""

	def __init__(self, host_key_fingerprint: str, host_key_type: str = ""):
		self.name = "stand-in-ssh-conn"
		self.enabled = True
		self.host = HOST
		self.port = PORT
		self.username = USER
		self.auth_method = "Password"
		self.host_key_fingerprint = host_key_fingerprint
		self.host_key_type = host_key_type

	def get_password(self, field, raise_exception=True):
		if field == "password":
			return PASSWORD
		if field in ("private_key", "private_key_passphrase"):
			return None
		if raise_exception:
			raise KeyError(field)
		return None


def _make_transport(connection_doc, **limit_overrides) -> SSHExecTransport:
	t = object.__new__(SSHExecTransport)
	t.ssh_connection_name = connection_doc.name
	t.limits = {
		"connection_timeout_seconds": 10,
		"execution_timeout_seconds": 30,
		"idle_timeout_seconds": 15,
		"combined_output_max_bytes": 1024 * 1024,
		"stdout_max_bytes": 1024 * 1024,
		"stderr_max_bytes": 1024 * 1024,
	}
	t.limits.update(limit_overrides)
	t._connection_doc = connection_doc
	t._staging_dir = None
	t._run_id = str(uuid.uuid4())
	return t


def _real_fingerprint() -> tuple[str, str]:
	sock = socket.create_connection((HOST, PORT), timeout=10)
	transport = paramiko.Transport(sock)
	try:
		transport.start_client(timeout=10)
		server_key = transport.get_remote_server_key()
		return fingerprint_for_key(server_key), server_key.get_name()
	finally:
		transport.close()


@pytest.fixture(scope="module")
def real_fingerprint() -> str:
	fp, _ = _real_fingerprint()
	return fp


@pytest.mark.asyncio
async def test_wrong_fingerprint_fails_closed(real_fingerprint):
	"""Strict host-key pinning must refuse to connect on a mismatched fingerprint,
	and must never proceed to authenticate or execute anything."""
	wrong_fp = "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
	assert wrong_fp != real_fingerprint
	doc = StandInSSHConnection(host_key_fingerprint=wrong_fp)
	transport = _make_transport(doc)

	probe = await transport.probe()
	assert probe.reachable is False
	assert "key mismatch" in (probe.detail or "").lower()

	with pytest.raises(Exception, match="host key mismatch"):
		await transport.run(["echo", "should-not-execute"])


@pytest.mark.asyncio
async def test_correct_fingerprint_exec_and_staging_round_trip(real_fingerprint):
	"""Full round trip against the real server: probe, exec via the fake CLI
	fixture, then SFTP stage/remove."""
	doc = StandInSSHConnection(host_key_fingerprint=real_fingerprint)
	transport = _make_transport(doc)

	probe = await transport.probe()
	assert probe.reachable is True

	result = await transport.run(
		["python3", "/home/tester/fake_cli.py", "-p", "hello", "--output-format", "json"]
	)
	assert result.exit_code == 0
	assert not result.timed_out
	payload = json.loads(result.stdout)
	assert "session_id" in payload
	assert payload["result"].startswith("HELLO")

	with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
		tmp.write("live-ssh-transport-test-payload\n")
		local_path = tmp.name

	try:
		staged = await transport.stage_file(local_path, target_name="live_test.txt")
		check = await transport.run(["cat", staged.remote_path])
		assert check.exit_code == 0
		assert "live-ssh-transport-test-payload" in check.stdout

		await transport.remove_staged_file(staged)
		check_gone = await transport.run(["test", "-e", staged.remote_path])
		assert check_gone.exit_code != 0
	finally:
		os.unlink(local_path)
