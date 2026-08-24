"""
Tests for the App domain service functions (create_app_from_agent, update_app,
install_app).
Run with:
    bench --site hufai.localhost run-tests --app huf --module huf.ai.app_seeding.tests.test_app_creation
"""
import unittest

import frappe

from huf.ai.app_seeding.apps_loader import (
	cleanup_orphaned_apps,
	create_app_from_agent,
	install_app,
	update_app,
)


class TestAppCreation(unittest.TestCase):
	"""Acceptance tests for the App domain service functions."""

	def setUp(self):
		self.suffix = frappe.generate_hash(length=8).lower()
		self._created_app_ids = []
		self._created_agent_names = []

		self.agent_name = self._make_agent(f"tappc_agent_{self.suffix}")

	def tearDown(self):
		for app_id in self._created_app_ids:
			try:
				frappe.db.sql("DELETE FROM `tabHUF App` WHERE name = %s", app_id)
			except Exception:
				pass
		for agent_name in self._created_agent_names:
			try:
				frappe.db.sql("DELETE FROM `tabAgent` WHERE name = %s", agent_name)
			except Exception:
				pass
		frappe.set_user("Administrator")
		frappe.db.commit()

	def _app_id(self, label):
		app_id = f"tappc_{label}_{self.suffix}"
		self._created_app_ids.append(app_id)
		return app_id

	def _make_agent(self, name, **kwargs):
		"""Create a minimal Agent doc, tolerant of required-field variance
		across environments (seam so this test degrades gracefully rather
		than crashing when run outside a live bench). Extra ``kwargs`` are
		set on the doc (e.g. allow_file_upload=1, enable_ocr=1)."""
		if frappe.db.exists("Agent", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": name,
				"description": name,
				"prompt_mode": "Local",
				"instructions": "Test agent instructions for app-creation service tests.",
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		self._created_agent_names.append(doc.name)
		return doc.name

	# ------------------------------------------------------------------
	# create_app_from_agent
	# ------------------------------------------------------------------

	def test_create_app_from_agent_happy_path(self):
		"""A valid app_id/title/agent_name creates a HUF App record with the
		expected defaults."""
		app_id = self._app_id("happy")

		result = create_app_from_agent(
			app_id=app_id,
			title="Test App",
			agent_name=self.agent_name,
		)

		self.assertEqual(result["app_id"], app_id)
		self.assertEqual(result["title"], "Test App")
		self.assertEqual(result["route"], f"/apps/{app_id}")
		self.assertEqual(result["category"], "Other")
		self.assertTrue(frappe.db.exists("HUF App", app_id))

	def test_create_app_from_agent_rejects_unknown_agent(self):
		"""An agent_name that does not resolve to an existing Agent doc
		raises a ValidationError and creates no record."""
		app_id = self._app_id("badagent")

		with self.assertRaises(frappe.ValidationError):
			create_app_from_agent(
				app_id=app_id,
				title="Test App",
				agent_name=f"does-not-exist-{self.suffix}",
			)

		self.assertFalse(frappe.db.exists("HUF App", app_id))

	# ------------------------------------------------------------------
	# update_app
	# ------------------------------------------------------------------

	def test_update_app_applies_partial_updates(self):
		"""Only the fields passed to update_app are changed; other fields on
		the record are left untouched."""
		app_id = self._app_id("update")
		create_app_from_agent(
			app_id=app_id,
			title="Original Title",
			agent_name=self.agent_name,
			description="Original description",
			category="Create",
		)

		result = update_app(app_id, title="Updated Title")

		self.assertEqual(result["title"], "Updated Title")
		self.assertEqual(result["description"], "Original description")
		self.assertEqual(result["category"], "Create")

	def test_update_app_rejects_file_upload_capability_without_agent_support(self):
		"""update_app raises when capabilities={'file_upload': True} is
		requested but the linked Agent has allow_file_upload=0."""
		app_id = self._app_id("cap_reject")
		agent_name = self._make_agent(
			f"tappc_agent_noupload_{self.suffix}", allow_file_upload=0
		)
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		with self.assertRaises(frappe.ValidationError):
			update_app(app_id, capabilities={"file_upload": True})

	def test_update_app_accepts_ocr_capability_with_agent_support(self):
		"""update_app succeeds when capabilities={'ocr': True} is requested
		and the linked Agent has enable_ocr=1."""
		app_id = self._app_id("cap_accept")
		agent_name = self._make_agent(
			f"tappc_agent_ocr_{self.suffix}", enable_ocr=1
		)
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		result = update_app(app_id, capabilities={"ocr": True})

		self.assertIn("ocr", result.get("capabilities") or "")

	def test_update_app_rejects_audio_output_capability_without_agent_tts_model(self):
		"""update_app raises when capabilities={'audio_output': True} is
		requested but the linked Agent has no tts_model configured."""
		app_id = self._app_id("cap_reject_audio_output")
		agent_name = self._make_agent(f"tappc_agent_notts_{self.suffix}")
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		with self.assertRaises(frappe.ValidationError):
			update_app(app_id, capabilities={"audio_output": True})

	def test_update_app_accepts_audio_output_capability_with_agent_tts_model(self):
		"""update_app succeeds when capabilities={'audio_output': True} is
		requested and the linked Agent has a tts_model configured.

		The Agent DocType's own validate() checks that tts_model resolves to
		an AI Model with the 'Text-to-Speech' modality, so the field is set
		directly via frappe.db.set_value (bypassing that unrelated
		validation) rather than through doc.insert/save -- this test only
		needs tts_model to be a non-empty string on the fetched Agent doc,
		not a real, resolvable AI Model record."""
		app_id = self._app_id("cap_accept_audio_output")
		agent_name = self._make_agent(f"tappc_agent_tts_{self.suffix}")
		frappe.db.set_value("Agent", agent_name, "tts_model", "some-tts-model")
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		result = update_app(app_id, capabilities={"audio_output": True})

		self.assertIn("audio_output", result.get("capabilities") or "")

	def test_update_app_rejects_live_voice_capability_without_agent_voice_enabled(self):
		"""update_app raises when capabilities={'live_voice': True} is
		requested but the linked Agent has voice_enabled=0 (even if a
		voice_engine happens to be set)."""
		app_id = self._app_id("cap_reject_live_voice")
		agent_name = self._make_agent(f"tappc_agent_novoice_{self.suffix}")
		frappe.db.set_value("Agent", agent_name, "voice_enabled", 0)
		frappe.db.set_value("Agent", agent_name, "voice_engine", "litellm_realtime")
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		with self.assertRaises(frappe.ValidationError):
			update_app(app_id, capabilities={"live_voice": True})

	def test_update_app_accepts_live_voice_capability_and_warns_about_memory_gap(self):
		"""update_app succeeds when capabilities={'live_voice': True} is
		requested against an Agent with voice_enabled=1 and voice_engine set
		to a real, built-in engine ('litellm_realtime') -- but the resolved
		engine's capabilities() reports memory=False (per
		huf/ai/voice/README.md's documented gap: no shipped voice engine
		injects Agent memory into a live session), so the result should carry
		a non-blocking warning about it rather than raising."""
		app_id = self._app_id("cap_accept_live_voice")
		agent_name = self._make_agent(f"tappc_agent_voice_{self.suffix}")
		frappe.db.set_value("Agent", agent_name, "voice_enabled", 1)
		frappe.db.set_value("Agent", agent_name, "voice_engine", "litellm_realtime")
		create_app_from_agent(
			app_id=app_id,
			title="Capability App",
			agent_name=agent_name,
		)

		result = update_app(app_id, capabilities={"live_voice": True})

		self.assertIn("live_voice", result.get("capabilities") or "")
		self.assertTrue(
			any("memory" in warning.lower() for warning in result.get("warnings") or [])
		)

	# ------------------------------------------------------------------
	# cleanup_orphaned_apps (Phase 13 hardening regression)
	# ------------------------------------------------------------------

	def test_chat_created_app_survives_cleanup_orphaned_apps(self):
		"""Regression: an App created via create_app_from_agent (source_app="huf",
		source_file="chat") must NOT be deleted by cleanup_orphaned_apps, which
		runs on every bench migrate via sync_huf_apps().

		find_seed_dirs() deliberately skips scanning "huf" itself (the
		manifest-discovery pipeline is for *other* apps' huf/apps/*.json files),
		so a huf-sourced record can never appear in the `seen` set that
		cleanup_orphaned_apps uses to decide what survives a full sync -- before
		the fix, this meant every chat-created App was silently deleted on the
		very next migrate. Simulates exactly that: an empty `seen` set (as if
		find_seed_dirs() found nothing, which is always true for "huf"),
		asserting the record is NOT in the deleted list and still exists.
		"""
		app_id = self._app_id("survives_cleanup")
		create_app_from_agent(
			app_id=app_id,
			title="Should Survive Cleanup",
			agent_name=self.agent_name,
		)
		self.assertTrue(frappe.db.exists("HUF App", app_id))

		deleted = cleanup_orphaned_apps(seen=set())

		self.assertNotIn(app_id, deleted)
		self.assertTrue(
			frappe.db.exists("HUF App", app_id),
			"chat-created App must survive cleanup_orphaned_apps even with an "
			"empty `seen` set, since huf-sourced records are never scanned",
		)

	# ------------------------------------------------------------------
	# install_app
	# ------------------------------------------------------------------

	def test_install_app_is_idempotent(self):
		"""Calling install_app twice for the same app_id does not duplicate
		the record and does not error."""
		app_id = self._app_id("install")
		create_app_from_agent(
			app_id=app_id,
			title="Installable App",
			agent_name=self.agent_name,
		)
		frappe.db.set_value("HUF App", app_id, "enabled", 0)

		first = install_app(app_id)
		self.assertFalse(first["already_installed"])
		self.assertEqual(frappe.db.get_value("HUF App", app_id, "enabled"), 1)
		self.assertEqual(frappe.db.get_value("HUF App", app_id, "sync_status"), "Active")

		second = install_app(app_id)
		self.assertTrue(second["already_installed"])
		self.assertEqual(
			frappe.db.count("HUF App", {"app_id": app_id}),
			1,
			"install_app must not create duplicate records",
		)


if __name__ == "__main__":
	unittest.main()
