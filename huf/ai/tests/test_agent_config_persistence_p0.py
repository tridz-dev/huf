# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Phase 3 P0 regression tests for the Agent config-persistence contract
(`docs/testing/CURRENT_STATE.md` section 2, "Agent core"):

    load -> modify -> save -> reload -> runtime uses new value.

A field merely rendering in the React editor is not enough; every test here
does a real round-trip through `huf.ai.agent_config_api` against a real
Frappe DB (Layer B, `IntegrationTestCase`, run under `bench run-tests`).

Distinct from the existing `huf/ai/tests/test_agent_config_api.py` (which
covers narrow-section-read, cross-section rejection, and rename): this file
targets the five specific P0 scenarios called out for this track --
multi-section CRUD round-trip, the optimistic-concurrency stale-revision
reject, the two-coexisting-write-paths race (section API vs full-document
`.save()`, the backend equivalent of the frontend's `updateAgent`), system-
agent immutability, and the hidden-tab-still-PATCHable edge case.

Every Agent this file creates is named with the `_Test P31 Agent` prefix
(a distinctive marker for this task) to avoid collisions with fixtures any
concurrently-running test file/task might create against the same shared
bench.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_config_api import get_agent_section, update_agent_section
from huf.ai.tests.factories import make_agent, make_ai_provider_and_model, make_user


class TestAgentConfigPersistenceP0(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.provider, self.model = make_ai_provider_and_model()
		self._agent_names = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._agent_names:
			if frappe.db.exists("Agent", name):
				# System agents are undeletable via the normal on_trash hook
				# (agent.py::on_trash) -- flip the flag directly in the DB
				# (bypassing validate()) so teardown can still clean up a
				# fixture that was deliberately made a system agent mid-test.
				frappe.db.set_value("Agent", name, "is_system", 0)
				frappe.db.commit()
				frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
		frappe.db.delete("AI Model", {"name": self.model})
		frappe.db.delete("AI Provider", {"name": self.provider})
		frappe.db.commit()

	def _make_agent(self, **overrides):
		agent = make_agent(
			agent_name=f"_Test P31 Agent {frappe.generate_hash(length=8)}",
			provider=self.provider,
			model=self.model,
			**overrides,
		)
		self._agent_names.append(agent.name)
		return agent

	# -----------------------------------------------------------------
	# AGENT-001: full CRUD round-trip across >=2 sections.
	# load -> modify -> save -> reload -> runtime (frappe.get_doc) sees it.
	# -----------------------------------------------------------------
	def test_agent_001_multi_section_round_trip_survives_reload(self):
		agent = self._make_agent(description="original description")

		# Section 1: "general" -- change agent_name (rename path) + description.
		before_general = get_agent_section(agent.name, "general")
		new_description = "_Test P31 updated description"
		result_general = update_agent_section(
			agent.name,
			"general",
			{"description": new_description},
			before_general["modified"],
		)
		self.assertEqual(result_general["values"]["description"], new_description)

		# Section 2: "behavior" -- flip allow_chat + persist_conversation.
		before_behavior = get_agent_section(agent.name, "behavior")
		result_behavior = update_agent_section(
			agent.name,
			"behavior",
			{"allow_chat": 1, "persist_conversation": 1},
			before_behavior["modified"],
		)
		self.assertEqual(result_behavior["values"]["allow_chat"], 1)
		self.assertEqual(result_behavior["values"]["persist_conversation"], 1)

		# Reload from a *fresh* Document instance (not the in-memory `agent`
		# object mutated above) -- proves the write actually reached the DB,
		# not just the in-process object the API happened to return.
		reloaded = frappe.get_doc("Agent", agent.name)
		self.assertEqual(reloaded.description, new_description)
		self.assertEqual(reloaded.allow_chat, 1)
		self.assertEqual(reloaded.persist_conversation, 1)

		# "runtime uses new value": get_agent_section (the read path the
		# editor/runtime re-reads from) must reflect the same values too.
		refetched_general = get_agent_section(agent.name, "general")
		refetched_behavior = get_agent_section(agent.name, "behavior")
		self.assertEqual(refetched_general["values"]["description"], new_description)
		self.assertEqual(refetched_behavior["values"]["allow_chat"], 1)

	# -----------------------------------------------------------------
	# AGENT-014-equivalent: _assert_revision's optimistic-concurrency
	# check must reject a write whose expected_modified is stale.
	# -----------------------------------------------------------------
	def test_agent_014_stale_revision_write_is_rejected(self):
		agent = self._make_agent()

		# Load the section (captures agent.modified at time T0).
		stale_section = get_agent_section(agent.name, "behavior")

		# Someone else mutates the Agent out-of-band (T1 > T0), advancing
		# `modified` without going through the section API at all -- the
		# exact "changed after the section was loaded" scenario
		# _assert_revision (agent_config_api.py:~173) exists to catch.
		frappe.db.set_value("Agent", agent.name, "description", "_Test P31 out-of-band change")
		frappe.db.commit()

		with self.assertRaises(frappe.TimestampMismatchError):
			update_agent_section(
				agent.name,
				"behavior",
				{"allow_chat": 1},
				stale_section["modified"],
			)

		# Confirm the rejected write really did not apply.
		self.assertEqual(frappe.db.get_value("Agent", agent.name, "allow_chat"), 0)

	# -----------------------------------------------------------------
	# Two-write-path race: update_agent_section (revision-checked) vs the
	# backend equivalent of the frontend's full-document `updateAgent`
	# (agentApi.ts:643, which the frontend implements as a plain
	# `frappe.client.set_value`/`db.updateDoc`-style call with no revision
	# check at all -- the Python-side equivalent of "load the doc fresh and
	# .save() it" is `frappe.get_doc("Agent", name); doc.field = x; doc.save()`,
	# since there is no separate whitelisted "full update" Python function to
	# call directly). This test does NOT assume which path "should" win --
	# it establishes what actually happens today.
	# -----------------------------------------------------------------
	def test_two_write_paths_race_current_behavior(self):
		agent = self._make_agent(description="original description")

		# Step 1: section-API read captures revision T0.
		stale_section = get_agent_section(agent.name, "general")

		# Step 2: the OTHER write path -- a full-document load+save, mirroring
		# what the frontend's `updateAgent()` does (no revision/expected_modified
		# concept exists on that path at all). This advances `modified` to T1
		# and changes a field the section-API write below does NOT touch.
		full_doc = frappe.get_doc("Agent", agent.name)
		full_doc.description = "_Test P31 full-doc-path description"
		full_doc.save(ignore_permissions=True)
		frappe.db.commit()

		# Step 3: attempt the section-API write using the STALE revision
		# captured in Step 1 (T0), i.e. the section editor never re-fetched
		# after the full-document write landed.
		with self.assertRaises(frappe.TimestampMismatchError):
			update_agent_section(
				agent.name,
				"general",
				{"description": "_Test P31 section-path description"},
				stale_section["modified"],
			)

		# OBSERVED behavior (not assumed): _assert_revision compares
		# `agent_doc.modified` against `expected_modified` regardless of
		# *which* code path advanced `modified` -- a full-document `.save()`
		# advances `modified` exactly like a section-API write does, so it IS
		# caught by the stale-revision check the same way an out-of-band
		# section write would be. This means the section API's optimistic
		# lock DOES protect against staleness introduced by the *other*
		# write path too, as long as the stale caller re-uses an
		# `expected_modified` captured before the full-document write. What
		# is NOT protected (and this test does not exercise, since it is the
		# opposite direction): a full-document `.save()` happening AFTER a
		# section-API write has no revision check of its own and will
		# silently clobber it -- see the next test for that direction.
		reloaded = frappe.get_doc("Agent", agent.name)
		self.assertEqual(reloaded.description, "_Test P31 full-doc-path description")

	def test_full_doc_write_after_section_write_has_no_revision_check(self):
		"""The reverse direction of the race: full-document `.save()` (the
		`updateAgent`-equivalent path) has NO revision/expected_modified
		concept at all, so it clobbers a prior section-API write even
		without ever re-reading the section API's returned `modified` value.
		This is the concrete, current-behavior demonstration of the
		documented risk in CURRENT_STATE.md section 2 ("concurrent-save race
		between these two paths is untested") -- confirmed here, not
		"fixed": full-doc save wins unconditionally, no exception raised.
		"""
		agent = self._make_agent(description="original description")

		before = get_agent_section(agent.name, "general")
		update_agent_section(
			agent.name,
			"general",
			{"description": "_Test P31 section-write-first"},
			before["modified"],
		)

		# Full-document path loads whatever is now in the DB (so it is not
		# "stale" in the frappe.get_doc sense -- it has no expected_modified
		# to be stale about), changes an unrelated field, and saves. No
		# exception is raised anywhere in this path.
		full_doc = frappe.get_doc("Agent", agent.name)
		full_doc.description = "_Test P31 full-doc-write-second"
		full_doc.save(ignore_permissions=True)  # does NOT raise

		reloaded = frappe.get_doc("Agent", agent.name)
		self.assertEqual(reloaded.description, "_Test P31 full-doc-write-second")

	# -----------------------------------------------------------------
	# System-agent immutability: attempting to change `instructions` on a
	# system agent via update_agent_section must be rejected.
	# -----------------------------------------------------------------
	def test_system_agent_instructions_immutable_via_section_api(self):
		agent = self._make_agent(instructions="original system instructions")
		# is_system flips are themselves guarded (_validate_system_field_tamper)
		# but allowed for System Manager / Administrator, which setUp runs as.
		frappe.db.set_value("Agent", agent.name, "is_system", 1)
		frappe.db.commit()

		before = get_agent_section(agent.name, "general")
		self.assertEqual(before["values"]["instructions"], "original system instructions")

		# Non-System-Manager user WITH the "agent.edit" capability (Huf Manager
		# role -- see DEFAULT_ROLE_CAPABILITIES in huf/permissions.py) so the
		# request clears `check_permission("write")` and actually reaches
		# `_validate_system_agent_immutability` (agent.py:247), which is exempt
		# only for System Manager / install-flag contexts, not for every
		# non-manager user in general.
		editor = make_user(roles=("Huf Manager",))
		try:
			frappe.set_user(editor.name)
			with self.assertRaises(frappe.ValidationError):
				update_agent_section(
					agent.name,
					"general",
					{"instructions": "_Test P31 attempted tamper"},
					before["modified"],
				)
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("User", editor.name, ignore_permissions=True, force=True)

		# Confirm the value truly did not change.
		self.assertEqual(
			frappe.db.get_value("Agent", agent.name, "instructions"),
			"original system instructions",
		)

	# -----------------------------------------------------------------
	# Hidden-tab-still-saveable: a "hidden" section (per agent_modality in
	# AgentFormPage.tsx) remains backend-PATCHable via update_agent_section.
	# -----------------------------------------------------------------
	def test_hidden_tools_section_still_patchable_via_backend(self):
		"""AgentFormPage.tsx:465-467 documents that agent_modality hides the
		Tools/Knowledge/Skills tabs in the React editor for some modality
		values, but that those sections remain PATCH-able server-side. This
		test constructs an agent whose modality would hide the "tools"
		section in the UI, then calls update_agent_section("tools", ...)
		directly -- proving whether the backend actually still allows it
		(matching the documented comment) or whether backend-level
		enforcement has since been added (which would be a documentation-vs-
		code drift worth flagging).
		"""
		agent = self._make_agent(agent_modality="Voice")

		before = get_agent_section(agent.name, "tools")
		self.assertIn("agent_tool", before["values"])

		# OBSERVED: as of this write, agent_config_api.py's AGENT_SECTIONS /
		# update_agent_section contain no agent_modality-conditional gating
		# at all -- the "tools" section's fields are unconditionally
		# editable server-side regardless of agent_modality. This matches
		# CURRENT_STATE.md's claim (AgentFormPage.tsx:465-467 comment) that
		# hidden tabs remain PATCH-able. If this assertion ever starts
		# raising instead, that means backend enforcement was added since
		# and CURRENT_STATE.md/this comment are now stale -- flag for the
		# coordinator's bench-verification pass rather than silently
		# "fixing" this test to expect a throw.
		result = update_agent_section(
			agent.name,
			"tools",
			{"agent_tool": []},
			before["modified"],
		)
		self.assertEqual(result["section"], "tools")

		reloaded = frappe.get_doc("Agent", agent.name)
		self.assertEqual(reloaded.agent_modality, "Voice")
