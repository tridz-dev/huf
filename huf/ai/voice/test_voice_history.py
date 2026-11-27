"""Bench-less tests for voice session nonces (huf.ai.voice.history) and the
ElevenLabs webhook's use of them. Frappe is replaced by a small in-memory fake.
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

if isinstance(frappe, MagicMock):  # bench-less stub: decorators must not swallow the handler
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	import frappe.rate_limiter

	frappe.rate_limiter.rate_limit = lambda *a, **k: (lambda fn: fn)

from huf.ai.providers import elevenlabs_convai_api as webhook
from huf.ai.voice import history

NOW = datetime(2026, 11, 26, 12, 0, 0)


def _match(row, filters):
	for key, cond in filters.items():
		value = row.get(key)
		if isinstance(cond, list):
			op, arg = cond
			if op == "is" and arg == "not set":
				if value:
					return False
			elif op == "<":
				if value is None or not value < arg:
					return False
			elif op == "in":
				if value not in arg:
					return False
		elif value != cond:
			return False
	return True


class FakeFrappe:
	class UniqueValidationError(Exception):
		pass

	class DuplicateEntryError(Exception):
		pass

	class PermissionError(Exception):
		pass

	def __init__(self):
		self.rows = {}
		self.users = {"u1": 1, "u2": 1, "off": 0}
		self.session = SimpleNamespace(user="Guest")
		self.set_user_calls = []
		self.rowcount = 0
		self.db = SimpleNamespace(
			get_value=self._get_value,
			exists=lambda dt, f: any(_match(r, f) for r in self.rows.values()),
			set_value=self._set_value,
			sql=self._sql,
			is_duplicate_entry=lambda e: isinstance(e, self.UniqueValidationError),
			delete=self._delete,
			_cursor=SimpleNamespace(),
		)
		self._cache = {}
		self.has_perm = {"u1": True, "u2": True}

	def cache(self):
		c = MagicMock()
		c.get_value = self._cache.get
		c.set_value = lambda k, v, expires_in_sec=None: self._cache.__setitem__(k, v)
		return c

	def get_doc(self, d):
		fake = self
		name = f"VS-{len(self.rows) + 1}"

		class _Doc(SimpleNamespace):
			def insert(self, ignore_permissions=False):
				for field in ("nonce_hash", "provider_conversation_id"):
					v = d.get(field)
					if v and any(r.get(field) == v for r in fake.rows.values()):
						raise fake.UniqueValidationError(field)
				fake.rows[name] = {**d, "name": name}
				return SimpleNamespace(name=name)

		return _Doc()

	def _get_value(self, doctype, filters, fields=None, as_dict=False):
		if doctype == "User":
			return self.users.get(filters)
		for row in self.rows.values():
			if isinstance(filters, dict) and _match(row, filters):
				if isinstance(fields, list):
					return SimpleNamespace(**{f: row.get(f) for f in fields})
				return row.get(fields)
		return None

	def _set_value(self, doctype, name, values, update_modified=True):
		self.rows[name].update(values)

	def _sql(self, query, params):
		self.rowcount = 0
		for row in self.rows.values():
			if (
				row.get("nonce_hash") == params["h"]
				and row.get("agent") == params["agent"]
				and row.get("claim_kind") == "Nonce"
				and not row.get("consumed_at")
				and row["expires_at"] > params["now"]
			):
				if any(r.get("provider_conversation_id") == params["pcid"] for r in self.rows.values()):
					raise self.UniqueValidationError("pcid")
				row["consumed_at"] = params["now"]
				row["provider_conversation_id"] = params["pcid"]
				self.rowcount = 1
		self.db._cursor.rowcount = self.rowcount

	def _delete(self, doctype, filters):
		for name in filters["name"][1]:
			self.rows.pop(name, None)

	def get_all(self, doctype, filters=None, pluck=None, limit=None, ignore_permissions=False):
		return [r["name"] for r in self.rows.values() if _match(r, filters)][:limit]

	def has_permission(self, doctype, ptype, user=None):
		return self.has_perm.get(user, False)

	def set_user(self, user):
		self.set_user_calls.append(user)
		self.session.user = user


class VoiceCase(unittest.TestCase):
	def setUp(self):
		self.fake = _install_fake(self)


def _install_fake(case):
	f = FakeFrappe()
	access = {"allowed": {("PRIV", "u1"), ("PUB", "Guest"), ("PUB", "u1")}}
	f.access = access

	def check(agent_doc, user, **_):
		return (agent_doc.name, user) in access["allowed"]

	for patcher in (
		patch.object(history, "frappe", f),
		patch.object(history, "now_datetime", lambda: NOW),
		patch.object(
			history, "add_to_date", lambda d, hours=0, days=0: d + timedelta(hours=hours, days=days)
		),
		patch("huf.ai.agent.access.check_agent_access", check),
	):
		patcher.start()
		case.addCleanup(patcher.stop)
	return f


def agent(name):
	return SimpleNamespace(name=name, embed_enabled=1 if name == "PUB" else 0)


def mint(fake, ag="PRIV", user="u1", conversation=None):
	return history.mint_voice_session(ag, "elevenlabs_convai", user=user, conversation=conversation)


class TestVoiceSessions(VoiceCase):
	def test_nonce_stored_only_hashed_with_ttl(self):
		fake = self.fake
		nonce = mint(fake)
		row = next(iter(fake.rows.values()))
		self.assertEqual((row["nonce_hash"]), (history.hash_nonce(nonce)))
		self.assertNotIn((nonce), (str(fake.rows)))
		self.assertEqual((row["expires_at"]), (NOW + timedelta(hours=24)))
		self.assertEqual((row["user"]), ("u1"))
		self.assertGreaterEqual((len(nonce)), (40))

	def test_valid_nonce_attributes_recorded_user_on_private_agent(self):
		fake = self.fake
		nonce = mint(fake, conversation="C1")
		attr = history.claim_nonce(agent("PRIV"), nonce, "pc1")
		self.assertEqual(((attr.writer, attr.owner_user, attr.conversation)), (("u1", "u1", "C1")))
		self.assertEqual((fake.rows[attr.session_row]["provider_conversation_id"]), ("pc1"))
		self.assertTrue(history.is_duplicate("pc1"))

	def test_forged_nonce_is_not_claimed(self):
		fake = self.fake
		mint(fake)
		self.assertIsNone(history.claim_nonce(agent("PRIV"), "forged", "pc1"))
		self.assertIsNone(history.claim_nonce(agent("PRIV"), None, "pc1"))
		self.assertIsNone(history.claim_guest(agent("PRIV"), "pc1"))  # private: not saved

	def test_replayed_nonce_cannot_be_used_twice(self):
		fake = self.fake
		nonce = mint(fake)
		self.assertTrue(history.claim_nonce(agent("PRIV"), nonce, "pc1"))
		self.assertIsNone(history.claim_nonce(agent("PRIV"), nonce, "pc2"))

	def test_expired_nonce_falls_back_to_guest_check(self):
		fake = self.fake
		nonce = mint(fake)
		next(iter(fake.rows.values()))["expires_at"] = NOW - timedelta(seconds=1)
		self.assertIsNone(history.claim_nonce(agent("PRIV"), nonce, "pc1"))
		self.assertIsNone(history.find_nonce_agent(nonce))

	def test_cross_agent_nonce_does_not_authorise_and_is_untouched(self):
		fake = self.fake
		nonce = mint(fake, ag="PRIV")
		self.assertIsNone(history.claim_nonce(agent("PUB"), nonce, "pc1"))
		row = next(iter(fake.rows.values()))
		self.assertFalse(row.get("consumed_at"))
		attr = history.claim_guest(agent("PUB"), "pc1")
		self.assertIsNone(attr.owner_user)
		self.assertEqual((attr.writer), ("Administrator"))

	def test_revoked_access_rejects_and_keeps_dedupe_key(self):
		fake = self.fake
		nonce = mint(fake)
		fake.access["allowed"].discard(("PRIV", "u1"))
		self.assertIsNone(history.claim_nonce(agent("PRIV"), nonce, "pc1"))
		row = next(iter(fake.rows.values()))
		self.assertEqual((row["outcome"]), ("Rejected"))
		self.assertTrue(history.is_duplicate("pc1"))

	def test_user_without_create_permission_or_disabled_is_rejected(self):
		fake = self.fake
		fake.has_perm["u1"] = False
		self.assertIsNone(history.resolve_writer(agent("PRIV"), "u1"))
		fake.has_perm["u1"] = True
		fake.users["u1"] = 0
		self.assertIsNone(history.resolve_writer(agent("PRIV"), "u1"))

	def test_anonymous_nonce_needs_guest_access_and_embed(self):
		fake = self.fake
		nonce = mint(fake, ag="PUB", user=None)
		attr = history.claim_nonce(agent("PUB"), nonce, "pc1")
		self.assertIsNone(attr.owner_user)
		self.assertEqual((attr.writer), ("Administrator"))

	def test_guest_claim_dedupes_redelivery(self):
		self.assertTrue(history.claim_guest(agent("PUB"), "pc1"))
		with self.assertRaises(history.DuplicateCall):
			history.claim_guest(agent("PUB"), "pc1")

	def test_rejected_nonce_on_guest_agent_still_saves_anonymously(self):
		fake = self.fake
		nonce = mint(fake, ag="PUB", user="u2")  # u2 has no access to PUB as a user
		self.assertIsNone(history.claim_nonce(agent("PUB"), nonce, "pc1"))
		attr = history.claim_guest(agent("PUB"), "pc1")
		self.assertIsNone(attr.owner_user)

	def test_acting_as_restores_identity_on_error(self):
		fake = self.fake
		with self.assertRaises(RuntimeError):
			with history.acting_as("u1"):
				self.assertEqual((fake.session.user), ("u1"))
				raise RuntimeError
		self.assertEqual((fake.session.user), ("Guest"))

	def test_purge_removes_expired_and_old_claims_only(self):
		fake = self.fake
		nonce_live = mint(fake)
		fake.rows["old"] = {"name": "old", "expires_at": NOW - timedelta(days=2)}
		fake.rows["claimed_old"] = {"name": "claimed_old", "consumed_at": NOW - timedelta(days=8)}
		fake.rows["claimed_new"] = {"name": "claimed_new", "consumed_at": NOW - timedelta(days=1)}
		self.assertEqual((history.purge_expired()), (2))
		self.assertNotIn(("old"), (fake.rows))
		self.assertNotIn(("claimed_old"), (fake.rows))
		self.assertIn(("claimed_new"), (fake.rows))
		self.assertEqual((history.find_nonce_agent(nonce_live)), ("PRIV"))


# --- webhook ------------------------------------------------------------------


def _webhook_env(fake, payload_nonce, signature_ok=True, agents=("PRIV",)):
	fake.get_all_agents = [SimpleNamespace(name=a, voice_config='{"agent_id": "el"}') for a in agents]
	wf = MagicMock()
	wf.get_all = lambda *a, **k: fake.get_all_agents
	wf.get_doc = lambda dt, name=None: agent(name) if dt == "Agent" else MagicMock()
	wf.request.get_data.return_value = b"{}"
	wf.get_single.return_value.get_password.return_value = "secret"
	return wf


def _call(fake, nonce, signature_ok=True, pcid="pc1"):
	wf = _webhook_env(fake, nonce)
	data = {
		"agent_id": "el",
		"conversation_id": pcid,
		"conversation_initiation_client_data": {
			"dynamic_variables": {
				history.NONCE_VARIABLE: nonce,
				"huf_conversation_id": "OTHER",
				"lead_name": "X",
			}
		},
	}
	with (
		patch.object(webhook, "frappe", wf),
		patch.object(webhook, "_verify_webhook_signature", return_value=signature_ok),
		patch.object(webhook, "_save_call", return_value="RUN-1") as save,
	):
		result = webhook.handle_elevenlabs_webhook(type="post_call_transcription", data=data)
	return result, save


class TestVoiceWebhook(VoiceCase):
	def test_webhook_bad_signature_never_touches_nonce(self):
		fake = self.fake
		nonce = mint(fake)
		result, save = _call(fake, nonce, signature_ok=False)
		self.assertEqual((result), ({"status": "forbidden"}))
		save.assert_not_called()
		self.assertFalse(next(iter(fake.rows.values())).get("consumed_at"))

	def test_webhook_private_agent_valid_nonce_saves_as_user_then_dedupes(self):
		fake = self.fake
		nonce = mint(fake)
		result, save = _call(fake, nonce)
		self.assertEqual((result["status"]), ("success"))
		attr = save.call_args.args[1]
		self.assertEqual((attr.owner_user), ("u1"))
		self.assertEqual((fake.set_user_calls), (["u1", "Guest"]))
		row = next(iter(fake.rows.values()))
		self.assertEqual(((row["outcome"], row["agent_run"])), (("Attributed", "RUN-1")))
		again, save2 = _call(fake, nonce)
		self.assertEqual((again), ({"status": "duplicate"}))
		save2.assert_not_called()

	def test_webhook_private_agent_without_valid_nonce_is_not_saved(self):
		fake = self.fake
		result, save = _call(fake, "forged")
		self.assertEqual((result), ({"status": "error", "message": "Agent not accessible"}))
		save.assert_not_called()

	def test_webhook_guest_agent_without_nonce_saves_anonymously(self):
		fake = self.fake
		wf = _webhook_env(fake, None, agents=("PUB",))
		data = {"agent_id": "el", "conversation_id": "pc9"}
		with (
			patch.object(webhook, "frappe", wf),
			patch.object(webhook, "_verify_webhook_signature", return_value=True),
			patch.object(webhook, "_save_call", return_value="RUN-2") as save,
		):
			result = webhook.handle_elevenlabs_webhook(type="post_call_transcription", data=data)
		self.assertEqual((result["status"]), ("success"))
		self.assertIsNone(save.call_args.args[1].owner_user)

	def test_webhook_nonce_picks_among_shared_elevenlabs_agents(self):
		fake = self.fake
		fake.access["allowed"].add(("OTHER", "u1"))
		nonce = mint(fake, ag="PRIV")
		wf = _webhook_env(fake, nonce, agents=("OTHER", "PRIV"))
		data = {
			"agent_id": "el",
			"conversation_id": "pc3",
			"conversation_initiation_client_data": {"dynamic_variables": {history.NONCE_VARIABLE: nonce}},
		}
		with (
			patch.object(webhook, "frappe", wf),
			patch.object(webhook, "_verify_webhook_signature", return_value=True),
			patch.object(webhook, "_save_call", return_value="RUN-3") as save,
		):
			webhook.handle_elevenlabs_webhook(type="post_call_transcription", data=data)
		self.assertEqual((save.call_args.args[0].name), ("PRIV"))
