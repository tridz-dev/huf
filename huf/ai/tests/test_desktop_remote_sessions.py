# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""REAL tests for desktop-owned sessions and remote control (Desktop Remote Sessions R1).

Real users, a real Agent, real Agent Conversation / Agent Run rows and the live Redis cache. Huf
Desktop is played by a thread that talks to the whitelisted lease endpoints exactly as the desktop
main process does (register, poll ``list_pending_desktop_tool_calls``, answer through
``submit_desktop_tool_event``, always presenting the lease secret). A "web session" is the same
Frappe user calling the same endpoints WITHOUT the secret. The only patched infrastructure is
``frappe.enqueue`` (no worker is running; a queued run is drained explicitly where a test needs it).

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_desktop_remote_sessions
"""

import base64
import json
import time
import types
import unittest
from unittest import mock

import frappe
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from huf.ai import agent_chat
from huf.ai import agent_integration as ai
from huf.ai import desktop_executor as dx
from huf.ai import desktop_policy as dp
from huf.ai import desktop_sessions as ds
from huf.ai.conversation_manager import ConversationManager
from huf.ai.sdk_tools import create_agent_tools
from huf.ai.tests import desktop_test_helpers as h
from huf.ai.tools import desktop_workspace as dw
from huf.api.v1.endpoints.conversations import _to_public_shape

CAPS = ["fs.read", "fs.write", "fs.trash", "exec", "proc"]
TOOLS = ["desktop_read_file", "desktop_run_command", "desktop_process_start"]


def _b64(raw):
	return base64.b64encode(raw).decode("ascii")


class Device:
	"""A desktop's identity: a private key that never leaves this object."""

	def __init__(self):
		self.private = Ed25519PrivateKey.generate()
		self._last_ts = 0
		self.raw = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
		self.spki = self.private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
		self.device_id = dx.derive_device_id(self.raw)

	def registration(self, executor_id, ts=None, key="spki", signer=None):
		if ts is None:
			# Ed25519 is deterministic: two proofs in the same second would be identical and the
			# server (rightly) treats a repeated proof as a replay, so a real desktop uses a fresh ts.
			ts = max(int(time.time() * 1000), self._last_ts + 1)
			self._last_ts = ts
		message = dx.registration_proof_message(executor_id, self.device_id, ts)
		signature = (signer or self.private).sign(message)
		return {
			"device_id": self.device_id,
			"public_key": _b64(self.spki if key == "spki" else self.raw),
			"device_proof": _b64(signature),
			"proof_ts": ts,
		}


class RemoteBase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.owner = h.make_user("dxrs")
		cls.other = h.make_user("dxrs2")
		cls.provider = cls._ensure_provider()
		cls.model = cls._ensure_model(cls.provider)
		cls.tool_rows = [
			frappe.db.get_value("Agent Tool Function", {"tool_name": name}, "name") for name in TOOLS
		]
		cls._docs = []

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		h.delete_docs(cls._docs + [("User", cls.owner), ("User", cls.other)])

	@staticmethod
	def _ensure_provider():
		existing = frappe.db.get_value("AI Provider", {}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Remote Sessions Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	@staticmethod
	def _ensure_model(provider):
		existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"remote-sessions-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def setUp(self):
		frappe.set_user("Administrator")
		self._enq = mock.patch("frappe.enqueue")
		self._enq.start()
		self.addCleanup(self._enq.stop)
		self.leases = []
		self.made = []  # (doctype, name) in creation order
		self.device = Device()
		self.exec_id = f"exec-rs-{frappe.generate_hash(length=10)}"
		self.agent = None

	def tearDown(self):
		frappe.set_user(self.owner)
		for exec_id in self.leases:
			try:
				h.unregister_desktop_executor(executor_id=exec_id)
			except Exception:
				pass
		frappe.set_user("Administrator")
		for row in frappe.get_all(
			"Desktop Remote Audit", filters={"user": ["in", [self.owner, self.other]]}, pluck="name"
		):
			frappe.delete_doc("Desktop Remote Audit", row, ignore_permissions=True, force=True)
		for doctype, name in reversed(self.made):
			if doctype == "Agent Conversation":
				for dt in ("Agent Message", "Agent Run"):
					for row in frappe.get_all(dt, filters={"conversation": name}, pluck="name"):
						try:
							frappe.delete_doc(dt, row, ignore_permissions=True, force=True)
						except Exception:
							pass
			try:
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	# ---- builders
	def make_agent(self, **over):
		frappe.set_user("Administrator")
		doc = {
			"doctype": "Agent",
			"agent_name": f"remote-sessions-agent-{frappe.generate_hash(length=8)}",
			"instructions": "Remote sessions test agent instructions",
			"provider": self.provider,
			"model": self.model,
			"allow_all_users": 1,
			"persist_conversation": 1,
			"agent_tool": [{"tool": n} for n in self.tool_rows],
		}
		doc.update(over)
		agent = frappe.get_doc(doc)
		agent.insert(ignore_permissions=True)
		frappe.db.commit()
		self.made.append(("Agent", agent.name))
		self.agent = agent.name
		return agent

	def register(
		self, user=None, executor_id=None, device="default", remote_control=False, caps=None, ws=None, **kw
	):
		user = user or self.owner
		executor_id = executor_id or self.exec_id
		frappe.set_user(user)
		dev = self.device if device == "default" else device
		extra = dev.registration(executor_id) if dev else {}
		extra.update(kw)
		out = h.register_desktop_executor(
			executor_id=executor_id,
			protocol_version=1,
			app_version="0.1",
			platform="darwin",
			workspace=ws or h.workspace(),
			capabilities=caps or CAPS,
			remote_control=remote_control,
			device_label="Test MacBook",
			**extra,
		)
		if executor_id not in self.leases:
			self.leases.append(executor_id)
		return out

	def track_conversation(self, name):
		self.made.append(("Agent Conversation", name))

	def hosted_conversation(self, agent=None, user=None, secret="auto"):
		"""A desktop-hosted conversation created the way Huf Desktop creates it."""
		agent = agent or self.agent
		frappe.set_user(user or self.owner)
		out = agent_chat.create_conversation(
			agent,
			execution_host="desktop",
			desktop_executor_id=self.exec_id,
			desktop_lease_secret=h.secret_of(self.exec_id) if secret == "auto" else secret,
		)
		self.track_conversation(out["conversation_id"])
		return out["conversation_id"]

	def send(self, conversation, secret=None, user=None, message="hello", **kw):
		"""A continuation of a conversation; ``secret`` is what the calling client presents."""
		frappe.set_user(user or self.owner)
		return agent_chat.send_message_to_conversation(
			conversation, message, desktop_lease_secret=secret, **kw
		)

	def pin_of(self, run_id):
		context = frappe.parse_json(frappe.db.get_value("Agent Run", run_id, "runtime_context") or "{}")
		return context.get("desktop")

	def pin_verifies(self, run_id, conversation):
		"""Does the run's stored pin verify FOR THAT RUN (the way the worker checks it)?"""
		run = frappe.get_doc("Agent Run", run_id)
		return dx.verify_pin(self.pin_of(run_id), conversation, run)

	def runs(self, conversation):
		return frappe.get_all("Agent Run", filters={"conversation": conversation}, pluck="name")

	def finish_runs(self, conversation):
		frappe.db.set_value("Agent Run", {"conversation": conversation}, "status", "Failed")
		frappe.db.commit()

	def expire_lease(self, exec_id=None):
		exec_id = exec_id or self.exec_id
		frappe.set_user(self.owner)
		h.unregister_desktop_executor(executor_id=exec_id)

	def play(self, call_id, script, poll_for_s=15, exec_id=None):
		"""Huf Desktop: wait for ``call_id`` in list_pending, then answer with ``script`` =
		[(sleep_s, kind, payload)]. Returns (thread, errors, seen) where seen holds the request."""
		exec_id = exec_id or self.exec_id
		seen = []

		def run():
			deadline = time.monotonic() + poll_for_s
			request = None
			while time.monotonic() < deadline and request is None:
				for req in h.list_pending_desktop_tool_calls(executor_id=exec_id):
					if req["call_id"] == call_id:
						request = req
				if request is None:
					time.sleep(0.1)
			if request is None:
				raise AssertionError("desktop never saw the call in list_pending")
			seen.append(request)
			for delay, kind, payload in script:
				time.sleep(delay)
				h.submit_desktop_tool_event(call_id=call_id, executor_id=exec_id, kind=kind, payload=payload)

		thread, errors = h.run_in_thread(run)
		return thread, errors, seen

	def finish(self, thread, errors, timeout=30):
		thread.join(timeout)
		self.assertFalse(thread.is_alive(), "desktop thread did not finish")
		self.assertEqual(errors, [])

	def audit_rows(self, action, device_id=None):
		previous = frappe.session.user
		frappe.set_user("Administrator")
		try:
			filters = {"action": action}
			if device_id:
				filters["device_id"] = device_id
			return frappe.get_all(
				"Desktop Remote Audit",
				filters=filters,
				fields=["name", "outcome", "user", "detail", "origin"],
			)
		finally:
			frappe.set_user(previous)


# --------------------------------------------------------------------------
# 1. Device identity and the lease secret
# --------------------------------------------------------------------------


class TestDeviceIdentity(RemoteBase):
	def test_register_with_a_proven_device_returns_secret_and_device_id(self):
		out = self.register()
		self.assertTrue(out["ok"])
		self.assertEqual(out["device_id"], self.device.device_id)
		self.assertTrue(out["lease_secret"] and len(out["lease_secret"]) >= 32)
		self.assertEqual(out["features"]["device"], True)
		lease = dx.find_device_lease(self.owner, self.device.device_id)
		self.assertEqual(lease["executor_id"], self.exec_id)
		self.assertEqual(lease["remote_control"], False)
		# only the hash is stored, never the secret
		self.assertNotIn(out["lease_secret"], json.dumps(dx._get_lease(self.exec_id), default=str))

	def test_raw_and_spki_public_keys_derive_the_same_device_id(self):
		other = Device()
		frappe.set_user(self.owner)
		a = h.register_desktop_executor(
			executor_id=self.exec_id,
			protocol_version=1,
			workspace=h.workspace(),
			capabilities=CAPS,
			**other.registration(self.exec_id, key="raw"),
		)
		self.leases.append(self.exec_id)
		self.assertEqual(a["device_id"], other.device_id)
		self.assertEqual(dx._decode_public_key(_b64(other.spki)), other.raw)

	def test_older_desktop_without_device_fields_registers_and_gets_a_secret(self):
		out = self.register(device=None)
		self.assertTrue(out["ok"])
		self.assertNotIn("device_id", out)
		self.assertTrue(out["lease_secret"])
		self.assertIsNone(dx._get_lease(self.exec_id).get("device_id"))

	def test_proof_signed_by_another_key_is_rejected(self):
		mallory = Device()
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id, signer=mallory.private)
		with self.assertRaises(frappe.PermissionError):
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)
		self.assertIsNone(dx._get_lease(self.exec_id))

	def test_device_id_that_does_not_match_the_key_is_rejected(self):
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id)
		reg["device_id"] = "0" * 32
		with self.assertRaises(frappe.ValidationError):
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)

	def test_a_device_id_without_a_proof_cannot_be_claimed(self):
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id)
		reg.pop("device_proof")
		with self.assertRaises(frappe.ValidationError):
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)

	def test_second_and_millisecond_timestamps_are_both_accepted(self):
		frappe.set_user(self.owner)
		seconds = self.device.registration(self.exec_id, ts=int(time.time()))
		self.assertTrue(
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**seconds,
			)["ok"]
		)
		self.leases.append(self.exec_id)
		millis = self.device.registration(self.exec_id)  # milliseconds
		self.assertGreater(millis["proof_ts"], 10**11)
		self.assertTrue(
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**millis,
			)["ok"]
		)
		# a millisecond timestamp far in the past is stale too
		stale = self.device.registration(self.exec_id, ts=int((time.time() - 3600) * 1000))
		with self.assertRaises(frappe.PermissionError):
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**stale,
			)

	def test_stale_proof_is_rejected(self):
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id, ts=int(time.time()) - 3600)
		with self.assertRaises(frappe.PermissionError):
			h.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)

	def test_a_proof_cannot_be_replayed(self):
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id)
		h.register_desktop_executor(
			executor_id=self.exec_id, protocol_version=1, workspace=h.workspace(), capabilities=CAPS, **reg
		)
		self.leases.append(self.exec_id)
		h.unregister_desktop_executor(executor_id=self.exec_id)
		with self.assertRaises(frappe.PermissionError):
			dx.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)

	def test_a_proof_for_one_executor_id_does_not_register_another(self):
		frappe.set_user(self.owner)
		reg = self.device.registration(self.exec_id)
		with self.assertRaises(frappe.PermissionError):
			dx.register_desktop_executor(
				executor_id=self.exec_id + "x",
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**reg,
			)

	def test_relaunch_with_a_new_executor_id_supersedes_the_old_lease(self):
		self.register()
		second = f"exec-rs-{frappe.generate_hash(length=10)}"
		out = self.register(executor_id=second)
		self.assertEqual(out["device_id"], self.device.device_id)
		self.assertIsNone(dx._get_lease(self.exec_id))
		self.assertEqual(dx.find_device_lease(self.owner, self.device.device_id)["executor_id"], second)

	def test_web_session_cannot_take_over_a_live_lease_by_reregistering_it(self):
		self.register()
		frappe.set_user(self.owner)  # same Frappe user, no secret
		with self.assertRaises(frappe.PermissionError):
			dx.register_desktop_executor(
				executor_id=self.exec_id, protocol_version=1, workspace=h.workspace(), capabilities=CAPS
			)
		# nor with a device identity of a different key
		mallory = Device()
		with self.assertRaises(frappe.PermissionError):
			dx.register_desktop_executor(
				executor_id=self.exec_id,
				protocol_version=1,
				workspace=h.workspace(),
				capabilities=CAPS,
				**mallory.registration(self.exec_id),
			)
		self.assertEqual(dx._get_lease(self.exec_id)["device_id"], self.device.device_id)

	def test_a_device_id_is_per_user(self):
		self.register()
		self.assertIsNone(dx.find_device_lease(self.other, self.device.device_id))
		frappe.set_user(self.other)
		self.assertEqual(ds.list_desktop_hosts(), [])

	def test_list_desktop_hosts_shows_only_public_fields(self):
		out = self.register(remote_control=True)
		frappe.set_user(self.owner)
		hosts = ds.list_desktop_hosts()
		self.assertEqual(len(hosts), 1)
		self.assertEqual(
			set(hosts[0]), {"device_id", "label", "online", "last_seen", "remote_control", "mode"}
		)
		self.assertTrue(hosts[0]["online"] and hosts[0]["remote_control"])
		blob = json.dumps(hosts)
		self.assertNotIn(out["lease_secret"], blob)
		self.assertNotIn(self.exec_id, blob)
		self.assertNotIn(_b64(self.device.spki), blob)
		self.assertNotIn(_b64(self.device.raw), blob)
		# offline: still listed through the last-seen marker only once it was bound to a conversation
		h.unregister_desktop_executor(executor_id=self.exec_id)
		self.assertIsNotNone(dx.device_last_seen(self.owner, self.device.device_id))


class TestLeaseSecret(RemoteBase):
	"""A web session of the same user, even one that knows the executor id, has no secret."""

	def setUp(self):
		super().setUp()
		self.out = self.register()
		self.secret = self.out["lease_secret"]
		self.call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		frappe.set_user(self.owner)

	def dispatch_in_thread(self, results):
		ctx = {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "w",
			"origin": "desktop",
		}

		def go():
			results.append(dx.dispatch("fs.read", {"path": "a.txt"}, ctx, call_id=self.call_id))

		return h.run_in_thread(go)

	def test_pending_calls_are_unreadable_without_the_secret(self):
		results = []
		thread, errors = self.dispatch_in_thread(results)
		play, play_errors, seen = self.play(
			self.call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "x"}})]
		)
		time.sleep(1.0)
		frappe.set_user(self.owner)
		for wrong in (None, "", "not-the-secret", self.secret + "x", self.secret[:-1]):
			with self.assertRaises(frappe.PermissionError, msg=repr(wrong)):
				dx.list_pending_desktop_tool_calls(executor_id=self.exec_id, lease_secret=wrong)
		self.finish(play, play_errors)
		self.finish(thread, errors)
		self.assertEqual(seen[0]["call_id"], self.call_id)

	def test_the_pending_listing_with_the_secret_works_and_carries_no_credential(self):
		results = []
		thread, errors = self.dispatch_in_thread(results)
		play, play_errors, seen = self.play(
			self.call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {}})]
		)
		self.finish(play, play_errors)
		self.finish(thread, errors)
		self.assertNotIn(self.secret, json.dumps(seen))

	def test_a_web_session_cannot_forge_a_result_even_with_the_executor_id(self):
		results = []
		thread, errors = self.dispatch_in_thread(results)
		# wait until the call is really pending, then forge as the same user, no secret
		deadline = time.monotonic() + 10
		while time.monotonic() < deadline and not h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
			time.sleep(0.1)
		frappe.set_user(self.owner)
		for kind, payload in (
			("result", {"ok": True, "data": {"content": "FORGED"}}),
			("ack", {}),
			("error", {"code": "internal", "message": "forged"}),
		):
			with self.assertRaises(frappe.PermissionError):
				dx.submit_desktop_tool_event(
					call_id=self.call_id, executor_id=self.exec_id, kind=kind, payload=payload
				)
			with self.assertRaises(frappe.PermissionError):
				dx.submit_desktop_tool_event(
					call_id=self.call_id,
					executor_id=self.exec_id,
					kind=kind,
					payload=payload,
					lease_secret="guess",
				)
		# the real desktop answers; the model sees ITS result, not the forgery
		h.submit_desktop_tool_event(call_id=self.call_id, executor_id=self.exec_id, kind="ack", payload={})
		h.submit_desktop_tool_event(
			call_id=self.call_id,
			executor_id=self.exec_id,
			kind="result",
			payload={"ok": True, "data": {"content": "REAL"}},
		)
		self.finish(thread, errors)
		self.assertTrue(results[0]["ok"])
		self.assertEqual(results[0]["data"]["content"], "REAL")

	def test_heartbeat_unregister_and_catalog_need_the_secret(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			dx.heartbeat_desktop_executor(
				executor_id=self.exec_id, workspace=h.workspace(), socket_connected=True
			)
		with self.assertRaises(frappe.PermissionError):
			dx.unregister_desktop_executor(executor_id=self.exec_id)
		with self.assertRaises(frappe.PermissionError):
			dx.register_desktop_catalog(executor_id=self.exec_id, catalog={"v": 1, "skills": []})
		# the lease survived the web session's attempts and works for the desktop
		self.assertIsNotNone(dx._get_lease(self.exec_id))
		self.assertTrue(h.heartbeat_desktop_executor(executor_id=self.exec_id, workspace=h.workspace())["ok"])
		self.assertTrue(
			h.register_desktop_catalog(executor_id=self.exec_id, catalog={"v": 1, "skills": []})["ok"]
		)

	def test_secret_in_the_request_header_is_accepted(self):
		frappe.set_user(self.owner)
		frappe.local.request = types.SimpleNamespace(headers={dx.LEASE_SECRET_HEADER: self.secret})
		try:
			self.assertEqual(dx.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		finally:
			frappe.local.request = None
		with self.assertRaises(frappe.PermissionError):
			dx.list_pending_desktop_tool_calls(executor_id=self.exec_id)

	def test_a_rotated_secret_invalidates_the_old_one(self):
		frappe.set_user(self.owner)
		second = h.register_desktop_executor(
			executor_id=self.exec_id,
			protocol_version=1,
			workspace=h.workspace(),
			capabilities=CAPS,
			**self.device.registration(self.exec_id),
		)
		self.assertNotEqual(second["lease_secret"], self.secret)
		with self.assertRaises(frappe.PermissionError):
			dx.list_pending_desktop_tool_calls(executor_id=self.exec_id, lease_secret=self.secret)
		self.assertEqual(
			dx.list_pending_desktop_tool_calls(executor_id=self.exec_id, lease_secret=second["lease_secret"]),
			[],
		)

	def test_the_secret_never_appears_in_a_web_readable_place(self):
		agent = self.make_agent(allow_remote_desktop=1)
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		run = result["agent_run_id"]
		frappe.set_user(self.owner)
		blobs = [
			json.dumps(result, default=str),
			json.dumps(frappe.get_doc("Agent Conversation", conv).as_dict(), default=str),
			json.dumps(frappe.get_doc("Agent Run", run).as_dict(), default=str),
			json.dumps(ds.list_desktop_hosts(), default=str),
			json.dumps(dx.resolve_desktop_ctx(self.exec_id, self.owner), default=str),
			json.dumps(_to_public_shape(frappe.get_doc("Agent Conversation", conv)), default=str),
		]
		for blob in blobs:
			self.assertNotIn(self.secret, blob)
			self.assertNotIn(dx._hash_secret(self.secret), blob)
			self.assertNotIn(_b64(self.device.spki), blob)
		del agent


# --------------------------------------------------------------------------
# 2-4. Hosted conversations, pinning, origin, remote gate
# --------------------------------------------------------------------------


class TestHostedConversation(RemoteBase):
	def setUp(self):
		super().setUp()
		self.out = self.register(remote_control=False)
		self.secret = self.out["lease_secret"]
		self.make_agent()

	# --- creation and the host badge
	def test_a_desktop_creates_a_hosted_conversation_bound_to_its_device(self):
		conv = self.hosted_conversation()
		doc = frappe.get_doc("Agent Conversation", conv)
		self.assertEqual(doc.execution_host, "desktop")
		self.assertEqual(doc.host_device_id, self.device.device_id)
		self.assertEqual(doc.host_workspace_fingerprint, h.FP)
		self.assertEqual(doc.host_label, "Test MacBook - my-project")

	def test_new_conversation_endpoint_creates_and_runs_pinned_to_the_desktop(self):
		frappe.set_user(self.owner)
		out = agent_chat.new_conversation(
			self.agent,
			"hi",
			execution_host="desktop",
			desktop_executor_id=self.exec_id,
			desktop_lease_secret=self.secret,
		)
		self.track_conversation(out["conversation_id"])
		self.assertTrue(out["run"]["queued"])
		pin = self.pin_of(out["run"]["agent_run_id"])
		self.assertEqual(pin["origin"], "desktop")
		self.assertEqual(pin["device_id"], self.device.device_id)
		self.assertTrue(self.pin_verifies(out["run"]["agent_run_id"], out["conversation_id"]))

	def test_the_host_is_exposed_for_the_web_badge(self):
		conv = self.hosted_conversation()
		frappe.set_user(self.owner)
		row = frappe.get_all(
			"Agent Conversation",
			filters={"name": conv},
			fields=["name", "execution_host", "host_device_id", "host_label"],
		)[0]
		self.assertEqual(row.execution_host, "desktop")
		self.assertEqual(row.host_label, "Test MacBook - my-project")
		shape = _to_public_shape(frappe.get_doc("Agent Conversation", conv))
		self.assertEqual(
			shape["host"], {"type": "desktop", "device_id": self.device.device_id, "label": row.host_label}
		)
		# a server conversation has no host block
		server = agent_chat.create_conversation(self.agent)
		self.track_conversation(server["conversation_id"])
		self.assertNotIn(
			"host", _to_public_shape(frappe.get_doc("Agent Conversation", server["conversation_id"]))
		)
		self.assertEqual(
			frappe.db.get_value("Agent Conversation", server["conversation_id"], "execution_host"), "server"
		)

	def test_a_web_session_cannot_create_a_hosted_conversation(self):
		frappe.set_user(self.owner)
		for secret in (None, "guess"):
			with self.assertRaises(frappe.PermissionError):
				agent_chat.create_conversation(
					self.agent,
					execution_host="desktop",
					desktop_executor_id=self.exec_id,
					desktop_lease_secret=secret,
				)

	def test_a_desktop_without_a_device_identity_cannot_host(self):
		legacy_id = f"exec-rs-{frappe.generate_hash(length=10)}"
		out = self.register(executor_id=legacy_id, device=None)
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			agent_chat.create_conversation(
				self.agent,
				execution_host="desktop",
				desktop_executor_id=legacy_id,
				desktop_lease_secret=out["lease_secret"],
			)

	def test_another_users_secret_and_lease_cannot_create_a_conversation_for_me(self):
		other_dev = Device()
		other_exec = f"exec-rs-{frappe.generate_hash(length=10)}"
		other_out = self.register(user=self.other, executor_id=other_exec, device=other_dev)
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			agent_chat.create_conversation(
				self.agent,
				execution_host="desktop",
				desktop_executor_id=other_exec,
				desktop_lease_secret=other_out["lease_secret"],
			)

	def test_a_hosted_conversation_is_never_picked_up_by_a_plain_chat(self):
		conv = self.hosted_conversation()
		frappe.set_user(self.owner)
		manager = ConversationManager(agent_name=self.agent, channel="Chat")
		plain = manager.get_or_create_conversation()
		self.track_conversation(plain.name)
		self.assertNotEqual(plain.name, conv)
		self.assertEqual(plain.execution_host, "server")

	# --- immutability (V1) and forged host changes
	def test_host_fields_are_immutable_and_cannot_be_forged(self):
		conv = self.hosted_conversation()
		self.send(conv, secret=self.secret)  # a first run exists now
		frappe.set_user(self.owner)
		for field, value in (
			("execution_host", "server"),
			("host_device_id", "f" * 32),
			("host_workspace_fingerprint", "deadbeef" * 2),
			("host_label", "Evil"),
		):
			doc = frappe.get_doc("Agent Conversation", conv)
			doc.set(field, value)
			with self.assertRaises(frappe.PermissionError, msg=field):
				doc.save()
			with self.assertRaises(frappe.PermissionError, msg=field):
				frappe.client.set_value("Agent Conversation", conv, field, value)
		row = frappe.db.get_value(
			"Agent Conversation",
			conv,
			["execution_host", "host_device_id", "host_workspace_fingerprint"],
			as_dict=True,
		)
		self.assertEqual(row.execution_host, "desktop")
		self.assertEqual(row.host_device_id, self.device.device_id)
		self.assertEqual(row.host_workspace_fingerprint, h.FP)
		# ordinary edits still work
		doc = frappe.get_doc("Agent Conversation", conv)
		doc.title = "renamed"
		doc.save()
		self.assertEqual(frappe.db.get_value("Agent Conversation", conv, "title"), "renamed")

	def test_a_server_conversation_cannot_be_flipped_to_desktop_hosted(self):
		frappe.set_user(self.owner)
		server = agent_chat.create_conversation(self.agent)["conversation_id"]
		self.track_conversation(server)
		doc = frappe.get_doc("Agent Conversation", server)
		doc.execution_host = "desktop"
		doc.host_device_id = self.device.device_id
		with self.assertRaises(frappe.PermissionError):
			doc.save()

	def test_a_web_insert_with_host_fields_is_refused(self):
		frappe.set_user(self.owner)
		doc = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"agent": self.agent,
				"session_id": f"forged-{frappe.generate_hash(length=8)}",
				"is_active": 1,
				"execution_host": "desktop",
				"host_device_id": self.device.device_id,
			}
		)
		with self.assertRaises(frappe.PermissionError):
			doc.insert()

	# --- run start pins to the device from any client
	def test_a_web_run_is_pinned_to_the_host_device_with_remote_origin(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 1)
		frappe.db.commit()
		self.register(remote_control=True)  # desktop-side switch on
		conv = self.hosted_conversation()
		# web: no secret, and a client-chosen executor id is ignored
		result = self.send(conv, desktop_executor_id="exec-someone-else-1")
		self.assertTrue(result["queued"])
		pin = self.pin_of(result["agent_run_id"])
		self.assertEqual(pin["executor_id"], self.exec_id)
		self.assertEqual(pin["origin"], "remote")
		self.assertEqual(pin["device_id"], self.device.device_id)
		self.assertTrue(self.pin_verifies(result["agent_run_id"], conv))
		self.assertEqual(result["desktop_tools"], {"available": True, "reason": None})

	def test_a_desktop_run_carries_desktop_origin(self):
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		self.assertEqual(self.pin_of(result["agent_run_id"])["origin"], "desktop")
		# a wrong secret is a web session, not the desktop
		self.finish_runs(conv)
		wrong = self.send(conv, secret="not-the-secret")
		self.assertEqual(wrong["code"], "remote_disabled")

	def test_desktop_offline_is_structured_and_never_a_server_run(self):
		conv = self.hosted_conversation()
		self.expire_lease()
		before = self.runs(conv)
		for secret in (None, self.secret):
			result = self.send(conv, secret=secret)
			self.assertFalse(result["success"])
			self.assertEqual(result["code"], "desktop_offline")
			self.assertEqual(result["error"], "desktop_offline")
			self.assertEqual(result["host_device_id"], self.device.device_id)
			self.assertIsInstance(result["last_seen"], int)
			self.assertLessEqual(result["last_seen"], int(time.time() * 1000))
			self.assertFalse(result["queued"])
		self.assertEqual(self.runs(conv), before)
		self.assertEqual(frappe.db.count("Agent Message", {"conversation": conv}), 0)

	def test_offline_fallback_attempts_from_the_client_are_refused(self):
		"""No executor id, another executor id, or a direct run_agent_sync: never a server run."""
		conv = self.hosted_conversation()
		self.expire_lease()
		frappe.set_user(self.owner)
		for kwargs in (
			{},
			{"desktop_executor_id": "exec-not-mine-01"},
			{"desktop_executor_id": self.exec_id},
		):
			result = ai.run_agent_sync(
				agent_name=self.agent, prompt="hi", conversation_id=conv, channel_id="Chat", **kwargs
			)
			self.assertEqual(result["code"], "desktop_offline")
		self.assertEqual(self.runs(conv), [])
		# the conversation does not silently become a server conversation either
		self.assertEqual(frappe.db.get_value("Agent Conversation", conv, "execution_host"), "desktop")

	def test_a_queued_run_drained_after_the_desktop_left_fails_instead_of_running_on_the_server(self):
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		run = result["agent_run_id"]
		self.expire_lease()
		frappe.set_user(self.owner)
		with mock.patch.object(ai, "AgentManager", side_effect=AssertionError("ran on the server")):
			ai._run_queued_agent(conversation_id=conv)
		row = frappe.db.get_value("Agent Run", run, ["status", "error_message"], as_dict=True)
		self.assertEqual(row.status, "Failed")
		self.assertIn("desktop_offline", row.error_message)

	def test_a_different_workspace_open_on_the_device_asks_for_a_rebind(self):
		conv = self.hosted_conversation()
		self.register(ws=h.workspace(fingerprint="aaaaaaaaaaaaaaaa"))
		result = self.send(conv, secret=h.secret_of(self.exec_id))
		self.assertEqual(result["code"], "workspace_changed")
		self.assertEqual(self.runs(conv), [])

	def test_a_non_owner_cannot_run_someone_elses_hosted_conversation(self):
		conv = self.hosted_conversation()
		frappe.set_user(self.other)
		conv_doc = frappe.get_doc("Agent Conversation", conv)
		ctx, status, error = ds.resolve_hosted_run(conv_doc, frappe.get_doc("Agent", self.agent), self.secret)
		self.assertIsNone(ctx)
		self.assertEqual(error["code"], "permission_denied")
		# the run API itself refuses too (the conversation is not accessible to another user)
		with self.assertRaises(frappe.PermissionError):
			ai.run_agent_sync(agent_name=self.agent, prompt="hi", conversation_id=conv, channel_id="Chat")
		self.assertEqual(self.runs(conv), [])

	# --- remote gate
	def test_remote_run_is_refused_when_the_desktop_switch_is_off(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 1)
		frappe.db.commit()
		conv = self.hosted_conversation()  # lease registered with remote_control False
		result = self.send(conv)
		self.assertEqual(result["code"], "remote_disabled")
		self.assertEqual(result["disabled_by"], "desktop")
		self.assertEqual(self.runs(conv), [])
		self.assertEqual(self.audit_rows("remote_run", self.device.device_id)[0].outcome, "blocked:desktop")

	def test_remote_run_is_refused_when_the_agent_flag_is_off(self):
		self.register(remote_control=True)
		conv = self.hosted_conversation()
		result = self.send(conv)  # agent allow_remote_desktop defaults to 0
		self.assertEqual(result["code"], "remote_disabled")
		self.assertEqual(result["disabled_by"], "agent")
		self.assertEqual(self.runs(conv), [])

	def test_remote_run_with_both_switches_on_has_no_other_restriction(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 1)
		frappe.db.commit()
		self.register(remote_control=True, ws=h.workspace(mode="full"))
		conv = self.hosted_conversation()
		result = self.send(conv)
		self.assertTrue(result["queued"])
		pin = self.pin_of(result["agent_run_id"])
		self.assertEqual(pin["origin"], "remote")
		self.assertTrue(pin["agent_policy"]["allow_remote_desktop"])
		self.assertEqual(self.audit_rows("remote_run", self.device.device_id)[-1].outcome, "allowed")
		# and the same run really executes on the desktop, uncapped, through the real handler
		call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		thread, errors, seen = self.play(
			call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "remote ok"}})]
		)
		frappe.set_user(self.owner)
		out = dw.handle_read_file(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.owner,
			_dx_pin=dw.issue_pin_token(result["agent_run_id"], self.exec_id, self.owner),
			agent_run_id=result["agent_run_id"],
			call_id=call_id,
		)
		self.finish(thread, errors)
		self.assertTrue(out["ok"], out)
		self.assertEqual(seen[0]["origin"], "remote")
		self.assertTrue(seen[0]["agent_policy"]["allow_remote_desktop"])
		self.assertEqual(seen[0]["device_id"], self.device.device_id)

	def test_desktop_origin_runs_do_not_need_the_remote_switches(self):
		# remote_control False and allow_remote_desktop 0: the desktop's own runs are unaffected
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		self.assertTrue(result["queued"])
		self.assertEqual(self.pin_of(result["agent_run_id"])["origin"], "desktop")

	def test_the_dispatcher_rechecks_the_remote_switch_when_it_is_turned_off_mid_conversation(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 1)
		frappe.db.commit()
		self.register(remote_control=True)
		conv = self.hosted_conversation()
		result = self.send(conv)
		self.assertTrue(result["queued"])
		# the user flips the desktop-side switch off (heartbeat reports it) before the run's tool call
		frappe.set_user(self.owner)
		h.heartbeat_desktop_executor(executor_id=self.exec_id, workspace=h.workspace(), remote_control=False)
		out = dw.handle_read_file(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.owner,
			_dx_pin=dw.issue_pin_token(result["agent_run_id"], self.exec_id, self.owner),
			agent_run_id=result["agent_run_id"],
			call_id=f"call-rs-{frappe.generate_hash(length=10)}",
		)
		self.assertFalse(out["ok"])
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	# --- forged origin
	def _forged_run(self, conv, **pin_over):
		"""A Huf User inserting an Agent Run whose pin claims desktop origin, without the server signature."""
		pin = {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "my-project",
			"origin": "desktop",
			"device_id": self.device.device_id,
		}
		pin.update(pin_over)
		frappe.set_user(self.owner)
		run = frappe.get_doc(
			{
				"doctype": "Agent Run",
				"agent": self.agent,
				"conversation": conv,
				"status": "Queued",
				"prompt": "forged",
				"runtime_context": frappe.as_json({"desktop": pin}),
			}
		)
		run.insert(ignore_permissions=True)
		frappe.db.commit()
		return run.name, pin

	def test_a_forged_desktop_origin_pin_is_treated_as_remote_and_refused(self):
		conv = self.hosted_conversation()
		run, _pin = self._forged_run(conv)  # unsigned, claims origin desktop
		frappe.set_user(self.owner)
		ctx = dw._validate_executor_context(
			self.exec_id, h.FP, self.owner, run, dw.issue_pin_token(run, self.exec_id, self.owner)
		)
		self.assertEqual(ctx["origin"], "remote")
		# lease remote_control is off: the dispatcher refuses, nothing is published
		out = dx.dispatch("fs.read", {"path": "a.txt"}, ctx, call_id="c-forged-1", agent_run_id=run)
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_a_signed_pin_whose_origin_was_edited_is_treated_as_remote(self):
		conv = self.hosted_conversation()
		pin = {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "my-project",
			"origin": "remote",
		}
		pin["sig"] = dx.sign_pin(pin, conv)
		pin["origin"] = "desktop"  # tampered after signing
		self.assertFalse(dx.verify_pin(pin, conv))
		context = {"desktop": pin}
		ctx = ai._desktop_ctx_from_runtime_context(
			context, run_owner=self.owner, conversation_owner=self.owner, conversation_id=conv
		)
		self.assertEqual(ctx["origin"], "remote")
		self.assertNotIn("agent_policy", ctx)
		# a valid signature for a DIFFERENT conversation does not transfer either
		good = {k: v for k, v in pin.items() if k != "origin"}
		good["origin"] = "desktop"
		good["sig"] = dx.sign_pin(good, "some-other-conversation")
		self.assertFalse(dx.verify_pin(good, conv))

	def test_a_signed_pin_survives_the_worker_round_trip_with_its_origin(self):
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		run = frappe.get_doc("Agent Run", result["agent_run_id"])
		context = frappe.parse_json(run.runtime_context)
		ctx = ai._desktop_ctx_from_runtime_context(
			context, run_owner=run.owner, conversation_owner=self.owner, conversation_id=conv, run=run
		)
		self.assertEqual(ctx["origin"], "desktop")
		self.assertEqual(ctx["device_id"], self.device.device_id)
		self.assertEqual(ctx["agent_policy"], dp.policy_from_agent(frappe.get_doc("Agent", self.agent)))

	def test_a_pin_for_another_device_is_dropped_when_the_executor_belongs_to_a_new_device(self):
		conv = self.hosted_conversation()
		result = self.send(conv, secret=self.secret)
		run = frappe.get_doc("Agent Run", result["agent_run_id"])
		context = frappe.parse_json(run.runtime_context)
		# the executor id is re-registered by a different device of the same user (after expiry)
		self.expire_lease()
		self.register(device=Device())
		frappe.set_user(self.owner)
		self.assertIsNone(
			ai._desktop_ctx_from_runtime_context(
				context, run_owner=run.owner, conversation_owner=self.owner, conversation_id=conv, run=run
			)
		)

	# --- rebind
	def test_rebind_moves_the_conversation_to_the_device_current_workspace(self):
		conv = self.hosted_conversation()
		self.register(ws=h.workspace(fingerprint="bbbbbbbbbbbbbbbb"))
		frappe.set_user(self.owner)
		self.assertEqual(self.send(conv, secret=h.secret_of(self.exec_id))["code"], "workspace_changed")
		out = ds.rebind_desktop_conversation(
			conversation=conv, desktop_lease_secret=h.secret_of(self.exec_id)
		)
		self.assertTrue(out["ok"])
		self.assertEqual(out["host_workspace_fingerprint"], "bbbbbbbbbbbbbbbb")
		row = frappe.db.get_value(
			"Agent Conversation",
			conv,
			["host_device_id", "host_workspace_fingerprint", "execution_host"],
			as_dict=True,
		)
		self.assertEqual(row.host_device_id, self.device.device_id)  # the device never changes
		self.assertEqual(row.host_workspace_fingerprint, "bbbbbbbbbbbbbbbb")
		self.assertTrue(self.send(conv, secret=h.secret_of(self.exec_id))["queued"])
		self.assertEqual(self.audit_rows("rebind", self.device.device_id)[0].outcome, "applied")

	def test_rebind_rules(self):
		conv = self.hosted_conversation()
		self.register(ws=h.workspace(fingerprint="cccccccccccccccc"))
		frappe.set_user(self.owner)
		# only a fingerprint the live lease reports
		secret = h.secret_of(self.exec_id)
		out = ds.rebind_desktop_conversation(
			conversation=conv, workspace_fingerprint="dddddddddddddddd", desktop_lease_secret=secret
		)
		self.assertEqual(out["error"]["code"], "workspace_changed")
		# not while a run is in flight
		run = frappe.get_doc(
			{"doctype": "Agent Run", "agent": self.agent, "conversation": conv, "status": "Queued"}
		)
		run.insert(ignore_permissions=True)
		out = ds.rebind_desktop_conversation(conversation=conv, desktop_lease_secret=secret)
		self.assertEqual(out["error"]["code"], "run_in_progress")
		self.finish_runs(conv)
		# not for someone else
		frappe.set_user(self.other)
		with self.assertRaises(frappe.PermissionError):
			ds.rebind_desktop_conversation(conversation=conv)
		# not to a server conversation
		frappe.set_user(self.owner)
		server = agent_chat.create_conversation(self.agent)["conversation_id"]
		self.track_conversation(server)
		with self.assertRaises(frappe.PermissionError):
			ds.rebind_desktop_conversation(conversation=server)
		# not while the device is offline
		self.expire_lease()
		frappe.set_user(self.owner)
		out = ds.rebind_desktop_conversation(conversation=conv)
		self.assertEqual(out["error"]["code"], "desktop_offline")

	def test_list_desktop_hosts_tracks_online_and_last_seen(self):
		self.hosted_conversation()
		frappe.set_user(self.owner)
		host = ds.list_desktop_hosts()[0]
		self.assertTrue(host["online"])
		self.assertEqual(host["label"], "Test MacBook")
		self.expire_lease()
		frappe.set_user(self.owner)
		host = ds.list_desktop_hosts()[0]
		self.assertFalse(host["online"])
		self.assertEqual(host["label"], "Test MacBook - my-project")
		self.assertIsInstance(host["last_seen"], int)


# --------------------------------------------------------------------------
# 5. Permission mode from the remote client
# --------------------------------------------------------------------------


class TestPermissionModeControl(RemoteBase):
	def setUp(self):
		super().setUp()
		self.register(remote_control=True, ws=h.workspace(mode="ask"))
		frappe.set_user(self.owner)

	def pending_control(self, timeout_s=15):
		deadline = time.monotonic() + timeout_s
		while time.monotonic() < deadline:
			for req in h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
				if req.get("kind") == "control":
					return req
			time.sleep(0.1)
		raise AssertionError("no control request reached the desktop")

	def play_control(self, applied_mode="auto", kind="result", payload=None, ack_first=True):
		seen = []

		def run():
			request = self.pending_control()
			seen.append(request)
			if ack_first:
				h.submit_desktop_tool_event(
					call_id=request["call_id"], executor_id=self.exec_id, kind="ack", payload={}
				)
			time.sleep(0.2)
			h.submit_desktop_tool_event(
				call_id=request["call_id"],
				executor_id=self.exec_id,
				kind=kind,
				payload=payload if payload is not None else {"ok": True, "data": {"mode": applied_mode}},
			)

		thread, errors = h.run_in_thread(run)
		return thread, errors, seen

	def test_mode_change_round_trip_returns_the_applied_mode_and_audits(self):
		thread, errors, seen = self.play_control("auto")
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.finish(thread, errors)
		self.assertEqual(out, {"ok": True, "applied_mode": "auto", "device_id": self.device.device_id})
		request = seen[0]
		self.assertEqual(request["kind"], "control")
		self.assertEqual(request["op"], dx.CONTROL_SET_PERMISSION_MODE)
		self.assertEqual(request["params"], {"mode": "auto", "fingerprint": h.FP})
		self.assertEqual(request["origin"], "remote")
		self.assertEqual(
			dx.find_device_lease(self.owner, self.device.device_id)["workspace"]["permission_mode"], "auto"
		)
		self.assertEqual(frappe.parse_json(json.dumps(ds.list_desktop_hosts()))[0]["mode"], "auto")
		rows = self.audit_rows("set_permission_mode", self.device.device_id)
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0].outcome, rows[0].user, rows[0].detail), ("applied", self.owner, "ask -> auto")
		)
		# the control request left nothing behind
		frappe.set_user(self.owner)
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_a_full_mode_is_changeable_too_no_cap(self):
		thread, errors, _seen = self.play_control("full")
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		self.finish(thread, errors)
		self.assertEqual(out["applied_mode"], "full")

	def test_mode_change_with_remote_control_off_is_refused_and_nothing_is_sent(self):
		self.register(remote_control=False)
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.assertFalse(out["ok"])
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		self.assertEqual(
			dx.find_device_lease(self.owner, self.device.device_id)["workspace"]["permission_mode"], "ask"
		)
		self.assertEqual(
			self.audit_rows("set_permission_mode", self.device.device_id)[0].outcome, "remote_disabled"
		)

	def test_another_users_device_looks_offline_and_is_untouched(self):
		frappe.set_user(self.other)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.assertEqual(out["error"]["code"], "desktop_offline")
		self.assertIsNone(out["error"]["last_seen"])
		frappe.set_user(self.owner)
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_offline_device_is_reported_with_last_seen(self):
		self.expire_lease()
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="ask")
		self.assertEqual(out["error"]["code"], "desktop_offline")
		self.assertIsInstance(out["error"]["last_seen"], int)

	def test_invalid_mode_and_unknown_device_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="root")
		out = ds.set_desktop_permission_mode(device_id="0" * 32, mode="ask")
		self.assertEqual(out["error"]["code"], "desktop_offline")
		out = ds.set_desktop_permission_mode(device_id="../../etc", mode="ask")
		self.assertEqual(out["error"]["code"], "desktop_offline")

	def test_a_desktop_that_reports_another_mode_is_not_taken_at_its_word(self):
		thread, errors, _seen = self.play_control("sandbox")
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.finish(thread, errors)
		self.assertEqual(out["error"]["code"], "mode_not_applied")
		self.assertEqual(out["error"]["applied_mode"], "sandbox")
		self.assertEqual(
			dx.find_device_lease(self.owner, self.device.device_id)["workspace"]["permission_mode"], "ask"
		)

	def test_a_desktop_error_is_surfaced(self):
		thread, errors, _seen = self.play_control(
			kind="error", payload={"code": "denied_by_user", "message": "the user declined"}
		)
		frappe.set_user(self.owner)
		out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.finish(thread, errors)
		self.assertFalse(out["ok"])
		self.assertEqual(out["error"]["code"], "denied_by_user")

	def test_no_answer_times_out_and_leaves_no_pending_request(self):
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 2):
			started = time.monotonic()
			out = ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		self.assertFalse(out["ok"])
		self.assertEqual(out["error"]["code"], "desktop_unreachable")
		self.assertLess(time.monotonic() - started, 12)
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		self.assertEqual(
			dx.find_device_lease(self.owner, self.device.device_id)["workspace"]["permission_mode"], "ask"
		)

	def test_a_web_session_cannot_answer_the_control_request_itself(self):
		results = []
		thread, errors = h.run_in_thread(
			lambda: results.append(
				ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
			)
		)
		request = self.pending_control()
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			dx.submit_desktop_tool_event(
				call_id=request["call_id"],
				executor_id=self.exec_id,
				kind="result",
				payload={"ok": True, "data": {"mode": "full"}},
			)
		with self.assertRaises(frappe.PermissionError):
			dx.list_pending_desktop_tool_calls(executor_id=self.exec_id)
		h.submit_desktop_tool_event(
			call_id=request["call_id"],
			executor_id=self.exec_id,
			kind="result",
			payload={"ok": True, "data": {"mode": "ask"}},
		)
		self.finish(thread, errors)
		self.assertEqual(results[0]["error"]["code"], "mode_not_applied")

	def test_the_control_event_is_published_to_the_lease_user_only(self):
		with mock.patch.object(dx.frappe, "publish_realtime") as pub:
			with mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
				ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="auto")
		events = [c.kwargs for c in pub.call_args_list if c.kwargs.get("event") == dx.CONTROL_EVENT]
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0]["user"], self.owner)
		self.assertNotIn("lease_secret", json.dumps(events[0]["message"]))


# --------------------------------------------------------------------------
# 6. Agent desktop access policy
# --------------------------------------------------------------------------


class TestAgentDesktopPolicy(RemoteBase):
	def setUp(self):
		super().setUp()
		self.out = self.register(remote_control=True)
		self.secret = self.out["lease_secret"]

	def names(self, agent, ctx_extra=None):
		frappe.set_user(self.owner)
		ctx = dx.resolve_desktop_ctx(self.exec_id, self.owner)
		ctx.update(ctx_extra or {})
		tools = create_agent_tools(frappe.get_doc("Agent", agent.name), desktop_ctx=ctx)
		return {t.name for t in tools} & set(TOOLS)

	def test_defaults_keep_the_current_behaviour_for_existing_agents(self):
		meta = frappe.get_meta("Agent")
		for cap in dp.CAPABILITIES:
			self.assertEqual(meta.get_field(f"desktop_access_{cap}").default, "allowed", cap)
		self.assertEqual(int(meta.get_field("allow_remote_desktop").default), 0)
		agent = self.make_agent()
		policy = dp.policy_from_agent(frappe.get_doc("Agent", agent.name))
		self.assertEqual(policy, dp.default_policy())
		# rows that existed before the fields were added read as allowed (column default), so an
		# agent that never configured anything exposes exactly what it used to
		self.assertEqual(self.names(agent), set(TOOLS))

	def test_an_off_capability_removes_its_tools_from_the_model(self):
		# running a process is running a command: cli=off removes the process tool as well
		for field, gone in (
			("desktop_access_cli", {"desktop_run_command", "desktop_process_start"}),
			("desktop_access_files", {"desktop_read_file"}),
			("desktop_access_processes", {"desktop_process_start"}),
		):
			agent = self.make_agent(**{field: "off"})
			self.assertEqual(self.names(agent), set(TOOLS) - gone, field)

	def test_ask_still_exposes_the_tool_and_is_carried_to_the_desktop(self):
		agent = self.make_agent(desktop_access_cli="ask")
		self.assertEqual(self.names(agent), set(TOOLS))
		self.assertEqual(dp.policy_from_agent(frappe.get_doc("Agent", agent.name))["cli"], "ask")

	def test_the_pinned_policy_wins_over_the_agent_document(self):
		agent = self.make_agent()  # everything allowed on the document
		pinned = dp.default_policy()
		pinned["cli"] = "off"
		self.assertEqual(
			self.names(agent, {"agent_policy": pinned}), set(TOOLS) - {"desktop_run_command", "desktop_process_start"}
		)

	def test_the_run_pin_carries_the_effective_policy_and_it_is_signed(self):
		agent = self.make_agent(
			desktop_access_processes="ask", desktop_access_browser="off", allow_remote_desktop=1
		)
		conv = self.hosted_conversation(agent=agent.name)
		result = self.send(conv, secret=self.secret)
		pin = self.pin_of(result["agent_run_id"])
		self.assertEqual(pin["agent_policy"]["processes"], "ask")
		self.assertEqual(pin["agent_policy"]["browser"], "off")
		self.assertEqual(pin["agent_policy"]["cli"], "allowed")
		self.assertTrue(pin["agent_policy"]["allow_remote_desktop"])
		self.assertTrue(self.pin_verifies(result["agent_run_id"], conv))
		run = frappe.get_doc("Agent Run", result["agent_run_id"])
		# widening the policy in the stored pin breaks the signature
		pin["agent_policy"]["browser"] = "allowed"
		self.assertFalse(dx.verify_pin(pin, conv, run))
		self.assertEqual(len(dp.policy_hash(pin["agent_policy"])), 16)

	def test_a_non_hosted_pinned_run_records_origin_and_policy_too(self):
		agent = self.make_agent(desktop_access_files="off")
		frappe.set_user(self.owner)
		conv = agent_chat.create_conversation(agent.name)["conversation_id"]
		self.track_conversation(conv)
		result = agent_chat.send_message_to_conversation(
			conv, "hi", desktop_executor_id=self.exec_id, desktop_lease_secret=self.secret
		)
		pin = self.pin_of(result["agent_run_id"])
		self.assertEqual(pin["origin"], "desktop")
		self.assertEqual(pin["agent_policy"]["files"], "off")
		self.assertEqual(pin["device_id"], self.device.device_id)
		# the same request without the secret is remote, and the agent flag is off
		self.finish_runs(conv)
		web = agent_chat.send_message_to_conversation(conv, "hi", desktop_executor_id=self.exec_id)
		self.assertEqual(web["desktop_tools"], {"available": False, "reason": "remote_disabled"})
		self.assertIsNone(self.pin_of(web["agent_run_id"]))

	def test_the_dispatcher_refuses_an_off_capability_even_if_the_tool_was_exposed(self):
		ctx = {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "w",
			"origin": "desktop",
			"agent_policy": {**dp.default_policy(), "cli": "off"},
		}
		frappe.set_user(self.owner)
		out = dx.dispatch("exec.run", {"command": "echo hi"}, ctx, call_id="c-policy-1")
		self.assertEqual(out["error"]["code"], "denied_by_policy")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		# files stay allowed: the same policy passes a read to the desktop
		call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		thread, errors, seen = self.play(
			call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {}})]
		)
		frappe.set_user(self.owner)
		ok = dx.dispatch("fs.read", {"path": "a"}, ctx, call_id=call_id)
		self.finish(thread, errors)
		self.assertTrue(ok["ok"])
		self.assertEqual(seen[0]["agent_policy"]["cli"], "off")

	def test_policy_maps_ops_and_tools_to_capabilities(self):
		self.assertEqual(dp.op_capability("mcp.call", {"server": "browser"}), "browser")
		self.assertEqual(dp.op_capability("mcp.call", {"server": "github"}), "local_mcp")
		self.assertEqual(dp.op_capability("exec.run"), "cli")
		self.assertEqual(dp.op_capability("proc.start"), "processes")
		self.assertEqual(dp.tool_capability("lbrowser__browser_click"), "browser")
		self.assertEqual(dp.tool_capability("lmcp__gh__list"), "local_mcp")
		self.assertTrue(dp.tool_allowed({"cli": "off"}, "desktop_read_file"))
		self.assertFalse(dp.tool_allowed({"cli": "off"}, "desktop_run_command"))
		# an unknown level is a deny; an unset one is the default
		self.assertEqual(dp.sanitize_policy({"cli": "root", "files": "ASK"})["cli"], "off")
		self.assertEqual(dp.sanitize_policy({"files": "ASK"})["files"], "ask")
		self.assertEqual(dp.sanitize_policy({"files": "ASK"})["cli"], "allowed")
		# a corrupted (non-dict) policy denies everything; no policy stays no policy
		self.assertEqual(set(dp.sanitize_policy("nope")[c] for c in dp.CAPABILITIES), {"off"})
		self.assertIsNone(dp.sanitize_policy(None))


# --------------------------------------------------------------------------
# 7. Hardening from the final review (FIX-BACKEND)
# --------------------------------------------------------------------------


class TestRunPinBinding(RemoteBase):
	"""H1: a signed pin is bound to the specific Agent Run it was written for."""

	def setUp(self):
		super().setUp()
		self.out = self.register(remote_control=False)
		self.secret = self.out["lease_secret"]
		self.make_agent()
		self.conv = self.hosted_conversation()
		# a desktop-origin run, as the desktop itself starts one (with the secret)
		self.run1 = self.send(self.conv, secret=self.secret)["agent_run_id"]
		self.pin = self.pin_of(self.run1)
		self.assertEqual(self.pin["origin"], "desktop")
		self.finish_runs(self.conv)

	def worker_ctx(self, run_name):
		run = frappe.get_doc("Agent Run", run_name)
		frappe.set_user("Administrator")  # what the orphan sweeper's drain job runs as
		try:
			return ai._build_execution_kwargs(run, frappe.parse_json(run.runtime_context))["desktop_ctx"]
		finally:
			frappe.set_user(self.owner)

	def tool_ctx(self, run_name):
		"""The ctx the tool handlers build for a run (what dispatch receives)."""
		frappe.set_user(self.owner)
		return dw._validate_executor_context(
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.owner,
			agent_run_id=run_name,
			_dx_pin=dw.issue_pin_token(run_name, self.exec_id, self.owner),
		)

	def web_insert_run(self, pin, prompt="attacker prompt"):
		"""What the web session can do: insert an Agent Run with permission checks ON."""
		frappe.set_user(self.owner)
		run = frappe.get_doc(
			{
				"doctype": "Agent Run",
				"agent": self.agent,
				"conversation": self.conv,
				"status": "Queued",
				"prompt": prompt,
				"runtime_context": frappe.as_json({"desktop": pin}),
			}
		)
		run.insert()
		frappe.db.commit()
		return run.name

	def new_job(self):
		"""A different worker job or request: it does not hold the claim an earlier one made."""
		frappe.local.flags.huf_dx_pin_claims = {}

	def test_an_honest_run_keeps_desktop_origin_on_both_sides(self):
		self.new_job()
		# the worker that drains the run claims its pin; the tool handlers of that same job then agree
		self.assertEqual(self.worker_ctx(self.run1)["origin"], "desktop")
		self.assertEqual(self.tool_ctx(self.run1)["origin"], "desktop")

	def test_a_web_session_cannot_send_a_finished_desktop_run_back_to_queued(self):
		"""D1, the exact replay from the review: the same web session (remote control off) sets an
		earlier desktop run back to Queued. The write is refused, and the run stays as it was."""
		self.new_job()
		self.assertEqual(self.worker_ctx(self.run1)["origin"], "desktop")  # the first, honest drain
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Agent Run", self.run1, "status", "Queued")
		self.assertEqual(frappe.db.get_value("Agent Run", self.run1, "status"), "Failed")
		# nor can the other inputs that steer a desktop-origin run be edited
		for field, value in (("prompt", "steer"), ("agent", "another"), ("conversation", "AC-other")):
			run = frappe.get_doc("Agent Run", self.run1)
			run.set(field, value)
			with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
				run.save()

	def test_a_run_that_drains_again_is_remote_even_when_the_requeue_bypasses_the_guard(self):
		"""Defense in depth: whatever puts the run back in the queue (a bug, a System Manager, a
		retry after a lost lease), the pin confers desktop origin to ONE execution only."""
		self.new_job()
		self.assertEqual(self.worker_ctx(self.run1)["origin"], "desktop")
		self.assertEqual(self.tool_ctx(self.run1)["origin"], "desktop")
		frappe.db.set_value("Agent Run", self.run1, "status", "Queued")
		frappe.db.commit()
		self.new_job()  # the sweeper's drain job
		again = self.worker_ctx(self.run1)
		self.assertEqual(again["origin"], "remote")
		self.assertNotIn("origin_ip", again)
		ctx = self.tool_ctx(self.run1)
		self.assertEqual(ctx["origin"], "remote")
		frappe.set_user(self.owner)
		out = dx.dispatch("fs.read", {"path": "a.txt"}, ctx, call_id="c-replay-1", agent_run_id=self.run1)
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_a_replayed_run_is_a_fresh_remote_decision_against_the_current_agent_flag(self):
		self.new_job()
		self.worker_ctx(self.run1)
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 1)
		frappe.db.commit()
		self.register(remote_control=True)  # the desktop switch is on and so is the agent's
		frappe.db.set_value("Agent Run", self.run1, "status", "Queued")
		frappe.db.commit()
		self.new_job()
		ctx = self.worker_ctx(self.run1)
		self.assertEqual(ctx["origin"], "remote")
		self.assertTrue(ctx["agent_policy"]["allow_remote_desktop"])  # read now, not from the old pin
		frappe.set_user("Administrator")
		frappe.db.set_value("Agent", self.agent, "allow_remote_desktop", 0)
		frappe.db.commit()
		self.new_job()
		frappe.db.set_value("Agent Run", self.run1, "status", "Queued")
		frappe.db.commit()
		tool = self.tool_ctx(self.run1)
		self.assertEqual(tool["origin"], "remote")
		self.assertFalse((tool.get("agent_policy") or {}).get("allow_remote_desktop"))
		frappe.set_user(self.owner)
		out = dx.dispatch("fs.read", {"path": "a.txt"}, tool, call_id="c-replay-2", agent_run_id=self.run1)
		self.assertEqual(out["error"]["code"], "remote_disabled")

	def test_only_one_of_two_racing_drains_claims_the_pin(self):
		self.new_job()
		first = dx.claim_desktop_pin(self.run1)
		second = dx.claim_desktop_pin(self.run1)
		self.assertTrue(first)
		self.assertIsNone(second)
		self.assertEqual(self.pin_of(self.run1)["consumed"], first)
		# the marker is not part of the signature: the pin still verifies for the run
		self.assertTrue(self.pin_verifies(self.run1, self.conv))
		# a run that has no desktop pin cannot be claimed at all
		self.assertIsNone(dx.claim_desktop_pin("no-such-run"))

	def test_the_normal_run_lifecycle_still_writes_status(self):
		"""The guard must not break the lifecycle: workers write with db.set_value / db_set and the
		system context saves; only a client save of a desktop run is refused."""
		self.new_job()
		frappe.set_user(self.owner)
		run = frappe.get_doc("Agent Run", self.run1)
		run.db_set("status", "Started")  # what _execute_agent_run does
		frappe.db.set_value("Agent Run", self.run1, {"status": "Failed", "error_message": "x"})  # _fail_queued_run
		self.assertEqual(frappe.db.get_value("Agent Run", self.run1, "status"), "Failed")
		frappe.set_user("Administrator")  # the sweeper and any system flow
		run = frappe.get_doc("Agent Run", self.run1)
		run.status = "Queued"
		run.save()
		self.assertEqual(frappe.db.get_value("Agent Run", self.run1, "status"), "Queued")
		# a client save that changes nothing guarded is unaffected, on a pinned run too
		frappe.set_user(self.owner)
		run = frappe.get_doc("Agent Run", self.run1)
		run.error_message = "seen by the owner"
		run.save()
		# and a run without a desktop pin in a normal conversation is not restricted
		plain = h.make_run(self.owner, {}, conversation=None)
		frappe.set_user(self.owner)
		doc = frappe.get_doc("Agent Run", plain)
		doc.status = "Queued"
		doc.save()
		self.assertEqual(frappe.db.get_value("Agent Run", plain, "status"), "Queued")
		h.delete_docs([("Agent Run", plain)])

	def test_a_pin_copied_into_a_new_run_is_remote_in_the_worker_and_at_dispatch(self):
		# the web session reads the pin over REST and inserts a NEW run in the same conversation with it
		copied = frappe.parse_json(frappe.as_json(self.pin))
		run2 = self.web_insert_run(copied)
		self.assertEqual(self.worker_ctx(run2)["origin"], "remote")
		self.assertEqual(self.tool_ctx(run2)["origin"], "remote")
		# and with remote control off the dispatcher refuses it
		ctx = self.tool_ctx(run2)
		frappe.set_user(self.owner)
		out = dx.dispatch("fs.read", {"path": "a.txt"}, ctx, call_id="c-copied-1", agent_run_id=run2)
		self.assertEqual(out["error"]["code"], "remote_disabled")

	def test_a_run_rewritten_and_requeued_with_a_new_prompt_loses_desktop_origin(self):
		frappe.set_user(self.owner)
		run = frappe.get_doc("Agent Run", self.run1)
		run.prompt = "something the desktop user never sent"
		run.status = "Queued"
		# the server now refuses this edit outright (status and prompt of a desktop run are pinned) ...
		with self.assertRaises(frappe.PermissionError):
			run.save()
		# ... and if the row is rewritten underneath it (a DB-level write), the pin no longer binds
		frappe.db.set_value(
			"Agent Run",
			self.run1,
			{"prompt": "something the desktop user never sent", "status": "Queued"},
			update_modified=False,
		)
		frappe.db.commit()
		self.assertEqual(self.worker_ctx(self.run1)["origin"], "remote")
		self.assertEqual(self.tool_ctx(self.run1)["origin"], "remote")

	def test_a_web_session_cannot_rewrite_runtime_context_of_an_existing_run(self):
		frappe.set_user(self.owner)
		run = frappe.get_doc("Agent Run", self.run1)
		forged = frappe.parse_json(run.runtime_context)
		forged["desktop"]["origin"] = "desktop"
		forged["desktop"]["agent_policy"] = {"cli": "allowed"}
		run.runtime_context = frappe.as_json(forged)
		with self.assertRaises(frappe.PermissionError):
			run.save()
		# through the same path REST set_value uses
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Agent Run", self.run1, "runtime_context", frappe.as_json(forged))

	def test_a_pin_is_bound_to_its_conversation_agent_and_creation_too(self):
		run = frappe.get_doc("Agent Run", self.run1)
		for field, value in (
			("conversation", "AC-other"),
			("agent", "another-agent"),
			("creation", "2001-01-01 00:00:00.000000"),
		):
			other = frappe._dict(name=run.name, conversation=run.conversation, agent=run.agent, creation=run.creation, prompt=run.prompt)
			other[field] = value
			self.assertFalse(dx.verify_pin(self.pin, run.conversation, other), field)

	def test_an_old_run_no_longer_confers_desktop_origin(self):
		run = frappe.get_doc("Agent Run", self.run1)
		old = "2001-01-01 00:00:00.000000"
		frappe.db.set_value("Agent Run", self.run1, "creation", old, update_modified=False)
		run.creation = old
		pin = dict(self.pin)
		pin.pop("sig")
		pin["sig"] = dx.sign_pin(pin, self.conv, run)  # a genuine, correctly signed, but ancient pin
		frappe.db.set_value(
			"Agent Run", self.run1, "runtime_context", frappe.as_json({"desktop": pin}), update_modified=False
		)
		self.assertEqual(self.worker_ctx(self.run1)["origin"], "remote")
		self.assertEqual(self.tool_ctx(self.run1)["origin"], "remote")


class TestOriginIp(RemoteBase):
	"""D13: the client address of a remote run reaches the desktop and the audit log."""

	def setUp(self):
		super().setUp()
		self.register(remote_control=True, ws=h.workspace(mode="full"))
		self.make_agent(allow_remote_desktop=1)
		self.conv = self.hosted_conversation()
		self._had_request = getattr(frappe.local, "request", None)
		self._had_ip = getattr(frappe.local, "request_ip", None)

	def tearDown(self):
		frappe.local.request = self._had_request
		frappe.local.request_ip = self._had_ip
		super().tearDown()

	def as_request(self, remote_addr, forwarded=None):
		headers = {"X-Forwarded-For": forwarded} if forwarded else {}
		frappe.local.request = types.SimpleNamespace(remote_addr=remote_addr, headers=headers, path="/", method="POST")
		# what Frappe itself derives (it trusts X-Forwarded-For): the value the huf code must NOT use
		frappe.local.request_ip = forwarded or remote_addr

	def test_clean_ip_accepts_only_ip_literals(self):
		self.assertEqual(dx.clean_ip("203.0.113.7"), "203.0.113.7")
		self.assertEqual(dx.clean_ip(" 2001:db8::1 "), "2001:db8::1")
		for junk in ("203.0.113.7, 198.51.100.9", "evil.example.com", "<script>", "", None, "1.2.3", "999.1.1.1"):
			self.assertEqual(dx.clean_ip(junk), "", repr(junk))

	def test_a_remote_run_carries_the_requests_address_to_the_desktop_and_the_audit(self):
		self.as_request("203.0.113.7", forwarded="198.51.100.9")  # a spoofed X-Forwarded-For
		result = self.send(self.conv)
		self.assertTrue(result["queued"], result)
		pin = self.pin_of(result["agent_run_id"])
		self.assertEqual(pin["origin"], "remote")
		self.assertEqual(pin["origin_ip"], "203.0.113.7")  # the socket peer, never the header
		self.assertTrue(self.pin_verifies(result["agent_run_id"], self.conv))
		frappe.set_user("Administrator")
		row = frappe.get_all(
			"Desktop Remote Audit",
			filters={"action": "remote_run", "outcome": "allowed", "device_id": self.device.device_id},
			fields=["ip_address"],
		)[-1]
		self.assertEqual(row.ip_address, "203.0.113.7")
		# the same run, dispatched by the worker (no request any more), sends it in the call
		frappe.local.request = None
		frappe.set_user(self.owner)  # the desktop thread runs as the lease owner, not the audit reader
		call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		thread, errors, seen = self.play(
			call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "ok"}})]
		)
		frappe.set_user(self.owner)
		run_id = result["agent_run_id"]
		out = dw.handle_read_file(
			path="a.txt",
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.owner,
			_dx_pin=dw.issue_pin_token(run_id, self.exec_id, self.owner),
			agent_run_id=run_id,
			call_id=call_id,
		)
		self.finish(thread, errors)
		self.assertTrue(out["ok"], out)
		self.assertEqual(seen[0]["origin"], "remote")
		self.assertEqual(seen[0]["origin_ip"], "203.0.113.7")

	def test_a_forged_origin_ip_in_the_pin_is_not_trusted_and_a_desktop_call_carries_none(self):
		self.as_request("203.0.113.7")
		result = self.send(self.conv)
		run_id = result["agent_run_id"]
		context = frappe.parse_json(frappe.db.get_value("Agent Run", run_id, "runtime_context"))
		context["desktop"]["origin_ip"] = "10.0.0.1"  # unsigned edit: the signature no longer verifies
		frappe.db.set_value("Agent Run", run_id, "runtime_context", frappe.as_json(context), update_modified=False)
		frappe.db.commit()
		frappe.local.request = None
		frappe.set_user(self.owner)
		ctx = dw._validate_executor_context(
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.owner,
			agent_run_id=run_id,
			_dx_pin=dw.issue_pin_token(run_id, self.exec_id, self.owner),
		)
		self.assertNotIn("origin_ip", ctx)
		self.assertEqual(ctx["origin"], "remote")
		# a desktop-origin ctx never sends an address, even if one is present
		call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		thread, errors, seen = self.play(
			call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {"content": "ok"}})]
		)
		frappe.set_user(self.owner)
		out = dx.dispatch(
			"fs.read", {"path": "a.txt"}, {**ctx, "origin": "desktop", "origin_ip": "203.0.113.7"}, call_id=call_id
		)
		self.finish(thread, errors)
		self.assertTrue(out["ok"], out)
		self.assertEqual(seen[0]["origin"], "desktop")
		self.assertNotIn("origin_ip", seen[0])


class TestMissingOriginFailsClosed(RemoteBase):
	"""H5 (backend half): a call with no or an unknown origin is a REMOTE call."""

	def setUp(self):
		super().setUp()
		self.register(remote_control=False)
		self.make_agent()
		frappe.set_user(self.owner)

	def ctx(self, **extra):
		ctx = {"executor_id": self.exec_id, "fingerprint": h.FP, "user": self.owner, "label": "w"}
		ctx.update(extra)
		return ctx

	def test_a_ctx_without_origin_is_refused_while_remote_control_is_off(self):
		frappe.set_user(self.owner)
		out = dx.dispatch("fs.read", {"path": "a.txt"}, self.ctx(), call_id="c-noorigin-1")
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def test_an_unknown_origin_is_refused_too(self):
		frappe.set_user(self.owner)
		for junk in ("admin", "", None, 1, "DESKTOP"):
			out = dx.dispatch("fs.read", {"path": "a.txt"}, self.ctx(origin=junk), call_id=f"c-junk-{junk}")
			self.assertEqual(out["error"]["code"], "remote_disabled", repr(junk))

	def test_an_explicit_desktop_origin_still_goes_through(self):
		call_id = f"call-rs-{frappe.generate_hash(length=10)}"
		thread, errors, seen = self.play(call_id, [(0.1, "ack", {}), (0.1, "result", {"ok": True, "data": {}})])
		frappe.set_user(self.owner)
		out = dx.dispatch("fs.read", {"path": "a.txt"}, self.ctx(origin="desktop"), call_id=call_id)
		self.finish(thread, errors)
		self.assertTrue(out["ok"])
		self.assertEqual(seen[0]["origin"], "desktop")


class TestPolicyCeilingHoles(RemoteBase):
	"""M1: deny always wins, and nothing an agent leaves unmapped slips through."""

	def setUp(self):
		super().setUp()
		self.register(remote_control=True, caps=CAPS + ["skills.exec"])
		frappe.set_user(self.owner)

	def ctx(self, policy):
		return {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "w",
			"origin": "desktop",
			"agent_policy": policy,
		}

	def denied(self, op, params, policy):
		frappe.set_user(self.owner)
		out = dx.dispatch(op, params, self.ctx(policy), call_id=f"c-{frappe.generate_hash(length=8)}")
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])
		return out

	def test_cli_off_also_blocks_proc_start_and_skill_exec(self):
		policy = {**dp.default_policy(), "cli": "off"}
		for op, params in (
			("proc.start", {"name": "dev", "command": "node server.js", "cwd": "."}),
			("skill.exec", {"skill": "x", "path": "run.sh", "args": []}),
			("exec.run", {"command": "ls"}),
		):
			out = self.denied(op, params, policy)
			self.assertEqual(out["error"]["code"], "denied_by_policy", op)
			self.assertIn("cli", out["error"]["message"], op)

	def test_cli_off_removes_the_process_start_and_skill_run_tools(self):
		agent = self.make_agent(desktop_access_cli="off")
		ctx = dx.resolve_desktop_ctx(self.exec_id, self.owner)
		tools = {t.name for t in create_agent_tools(frappe.get_doc("Agent", agent.name), desktop_ctx=ctx)}
		self.assertNotIn("desktop_run_command", tools)
		self.assertNotIn("desktop_process_start", tools)
		self.assertNotIn("desktop_skill_run", tools)
		self.assertEqual(dp.tool_capabilities("desktop_process_start"), ("processes", "cli"))

	def test_installs_off_blocks_an_install_command_and_only_that(self):
		policy = {**dp.default_policy(), "installs": "off"}
		for command in ("npm install left-pad", "pip install requests", "sudo apt-get install -y jq", "cd x && pnpm add y"):
			out = self.denied("exec.run", {"command": command}, policy)
			self.assertEqual(out["error"]["code"], "denied_by_policy", command)
			self.assertIn("installs", out["error"]["message"], command)
		out = self.denied("proc.start", {"name": "i", "command": "yarn add z", "cwd": "."}, policy)
		self.assertEqual(out["error"]["code"], "denied_by_policy")
		self.assertNotIn("installs", dp.op_capabilities("exec.run", {"command": "npm run build"}))
		self.assertNotIn("installs", dp.op_capabilities("exec.run", {"command": "git commit -m install"}))

	def test_an_unknown_level_denies_instead_of_allowing(self):
		self.assertEqual(dp.clean_level("root"), "off")
		self.assertEqual(dp.clean_level("Allowed "), "allowed")
		self.assertEqual(dp.clean_level(None), "allowed")
		out = self.denied("exec.run", {"command": "ls"}, {**dp.default_policy(), "cli": "bogus"})
		self.assertEqual(out["error"]["code"], "denied_by_policy")
		self.assertFalse(dp.tool_allowed({"cli": "bogus"}, "desktop_run_command"))
		# a corrupted, non-dict policy denies everything
		out = self.denied("fs.read", {"path": "a"}, "garbage")
		self.assertEqual(out["error"]["code"], "denied_by_policy")

	def test_deny_wins_when_one_of_several_capabilities_is_off(self):
		self.assertEqual(dp.blocked_capability({"processes": "allowed", "cli": "off"}, ("processes", "cli")), "cli")
		self.assertEqual(dp.blocked_capability({"processes": "off", "cli": "allowed"}, ("processes", "cli")), "processes")
		self.assertIsNone(dp.blocked_capability({"processes": "ask", "cli": "ask"}, ("processes", "cli")))


class TestRebindNeedsTheDesktopOrRemoteControl(RemoteBase):
	"""M2: a web session cannot re-point a hosted conversation while remote control is off."""

	def setUp(self):
		super().setUp()
		self.out = self.register(remote_control=False)
		self.make_agent()
		self.conv = self.hosted_conversation()
		self.register(ws=h.workspace(fingerprint="eeeeeeeeeeeeeeee"), remote_control=False)
		self.secret = h.secret_of(self.exec_id)
		frappe.set_user(self.owner)

	def fingerprint(self):
		return frappe.db.get_value("Agent Conversation", self.conv, "host_workspace_fingerprint")

	def test_a_web_session_without_the_secret_is_refused_and_nothing_changes(self):
		out = ds.rebind_desktop_conversation(conversation=self.conv)
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(self.fingerprint(), h.FP)
		self.assertEqual(self.audit_rows("rebind", self.device.device_id)[0].outcome, "remote_disabled")
		# a wrong secret is the same as none
		out = ds.rebind_desktop_conversation(conversation=self.conv, desktop_lease_secret="not-the-secret")
		self.assertEqual(out["error"]["code"], "remote_disabled")
		self.assertEqual(self.fingerprint(), h.FP)

	def test_the_desktop_with_its_secret_can_rebind(self):
		out = ds.rebind_desktop_conversation(conversation=self.conv, desktop_lease_secret=self.secret)
		self.assertTrue(out["ok"])
		self.assertEqual(self.fingerprint(), "eeeeeeeeeeeeeeee")
		self.assertEqual(self.audit_rows("rebind", self.device.device_id)[0].origin, "desktop")

	def test_a_web_session_can_rebind_once_remote_control_is_on(self):
		self.register(ws=h.workspace(fingerprint="eeeeeeeeeeeeeeee"), remote_control=True)
		frappe.set_user(self.owner)
		out = ds.rebind_desktop_conversation(conversation=self.conv)
		self.assertTrue(out["ok"])
		self.assertEqual(self.audit_rows("rebind", self.device.device_id)[0].origin, "remote")


class TestControlRequestReplay(RemoteBase):
	"""M8 (backend half): a control request is single-use and short-lived."""

	def setUp(self):
		super().setUp()
		self.register(remote_control=True, ws=h.workspace(mode="ask"))
		frappe.set_user(self.owner)

	def pending_control(self, timeout_s=15):
		deadline = time.monotonic() + timeout_s
		while time.monotonic() < deadline:
			for req in h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
				if req.get("kind") == "control":
					return req
			time.sleep(0.05)
		raise AssertionError("no control request reached the desktop")

	def raw_pending_controls(self):
		return [r for r in h.list_pending_desktop_tool_calls(executor_id=self.exec_id) if r.get("kind") == "control"]

	def test_the_request_carries_a_nonce_and_a_short_expiry(self):
		seen = []

		def desktop():
			seen.append(self.pending_control())

		thread, errors = h.run_in_thread(desktop)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		self.finish(thread, errors)
		request = seen[0]
		self.assertRegex(request["nonce"], r"^[0-9a-f]{32}$")
		self.assertEqual(request["expires_at"], request["issued_at"] + 1000)

	def test_a_control_request_is_delivered_by_the_pending_list_only_once(self):
		second = []

		def desktop():
			first = self.pending_control()  # the first poll takes it
			second.append((first, self.raw_pending_controls()))  # a poll after a "restart"

		thread, errors = h.run_in_thread(desktop)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 2):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		self.finish(thread, errors)
		first, again = second[0]
		self.assertEqual(first["kind"], "control")
		self.assertEqual(again, [], "a control request must not be handed out a second time")

	def test_heartbeat_listing_does_not_consume_a_control_request(self):
		seen = []

		def desktop():
			deadline = time.monotonic() + 10
			ids = []
			while time.monotonic() < deadline and not ids:
				ids = h.heartbeat_desktop_executor(
					executor_id=self.exec_id, workspace=h.workspace(mode="ask")
				).get("pending_call_ids") or []
				time.sleep(0.05)
			seen.append(ids)
			seen.append(self.pending_control())  # still available to the poll after a heartbeat saw it

		thread, errors = h.run_in_thread(desktop)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 3):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		self.finish(thread, errors)
		self.assertEqual(len(seen[0]), 1)
		self.assertEqual(seen[1]["call_id"], seen[0][0])

	def test_a_control_request_past_its_expiry_is_not_listed(self):
		def desktop():
			request = self.pending_control()
			# the same request is gone from the list once it has expired, claimed or not
			with mock.patch.object(dx, "_now_ms", return_value=request["expires_at"] + 5000):
				self.assertEqual(self.raw_pending_controls(), [])

		thread, errors = h.run_in_thread(desktop)
		with mock.patch.object(dx, "ACK_TIMEOUT_S", 2):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		self.finish(thread, errors)


class TestRealtimeDoesNotLeakPayloads(RemoteBase):
	"""L2: realtime rooms are per user, so an opted-in desktop gets only ids and fetches the rest."""

	def setUp(self):
		super().setUp()
		self.make_agent()

	def published(self, opaque):
		self.register(remote_control=True, opaque_realtime=opaque)
		frappe.set_user(self.owner)
		ctx = {
			"executor_id": self.exec_id,
			"fingerprint": h.FP,
			"user": self.owner,
			"label": "w",
			"origin": "desktop",
		}
		with mock.patch("frappe.publish_realtime") as publish, mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
			out = dx.dispatch("fs.read", {"path": "secret/plans.txt"}, ctx, call_id=f"c-leak-{frappe.generate_hash(length=8)}")
		self.assertEqual(out["error"]["code"], "desktop_unreachable", out)
		calls = [c for c in publish.call_args_list if c.kwargs.get("event") == dx.TOOL_CALL_EVENT]
		self.assertEqual(len(calls), 1)
		return calls[0].kwargs["message"]

	def test_an_opted_in_desktop_gets_a_payload_free_wake_event(self):
		message = self.published(True)
		self.assertEqual(set(message), {"v", "opaque", "kind", "executor_id", "call_id"})
		self.assertNotIn("secret/plans.txt", json.dumps(message))

	def test_a_legacy_desktop_still_gets_the_full_request(self):
		message = self.published(False)
		self.assertEqual(message["params"], {"path": "secret/plans.txt"})

	def test_the_control_event_is_opaque_for_an_opted_in_desktop(self):
		self.register(remote_control=True, opaque_realtime=True)
		frappe.set_user(self.owner)
		with mock.patch("frappe.publish_realtime") as publish, mock.patch.object(dx, "ACK_TIMEOUT_S", 1):
			ds.set_desktop_permission_mode(device_id=self.device.device_id, mode="full")
		message = [c.kwargs["message"] for c in publish.call_args_list if c.kwargs.get("event") == dx.CONTROL_EVENT][0]
		self.assertEqual(set(message), {"v", "opaque", "kind", "executor_id", "call_id"})
		self.assertNotIn("params", message)

	def test_the_lease_flag_and_feature_are_reported(self):
		out = self.register(opaque_realtime=True)
		self.assertTrue(out["features"]["opaque_realtime"])
		self.assertTrue(out["features"]["control_nonce"])
		self.assertTrue(dx._get_lease(self.exec_id)["opaque_realtime"])


if __name__ == "__main__":
	unittest.main()
