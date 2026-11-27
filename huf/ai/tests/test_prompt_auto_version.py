# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Auto-versioning of prompt saves, and title lookups across versions.

Runs against an in-memory stand-in for ``frappe`` so it needs no bench.
"""

import itertools
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.prompts import lineage, versioning


class _Throw(Exception):
	pass


class _Doc(SimpleNamespace):
	def __init__(self, fake, doctype, **kw):
		super().__init__(doctype=doctype, **kw)
		self._fake = fake

	def __getattr__(self, name):
		if name.startswith("_"):
			raise AttributeError(name)
		return None  # unset DocType fields read as None

	def check_permission(self, ptype):
		if not self._fake.allowed:
			raise _Throw

	def update(self, values):
		self.__dict__.update(values)

	def save(self, **_kw):
		self._fake.saves += 1
		self._fake.store(self)

	def insert(self, **_kw):
		n = next(self._fake.counter)
		self.name = f"{self.doctype[:3].upper()}-{n}"
		self.__dict__.setdefault("slug", f"slug-{n}")
		self.__dict__.setdefault("creation", n)
		self._fake.store(self)
		if not self.__dict__.get("prompt_group"):
			self.prompt_group = self.name
			self._fake.store(self)


class FakeFrappe:
	"""Tiny subset of frappe: tables as dicts, filters as equality maps."""

	def __init__(self):
		self.tables = {}
		self.counter = itertools.count(1)
		self.allowed = True
		self.saves = 0
		self.db = self
		self.flags = SimpleNamespace()

	# --- storage helpers
	def store(self, doc):
		row = {k: v for k, v in doc.__dict__.items() if not k.startswith("_")}
		self.tables.setdefault(doc.doctype, {})[doc.name] = row

	def add(self, doctype, name, **fields):
		self.tables.setdefault(doctype, {})[name] = {"name": name, "doctype": doctype, **fields}

	def _match(self, row, filters):
		return all(row.get(k) == v for k, v in filters.items())

	def _rows(self, doctype, filters):
		rows = self.tables.get(doctype, {}).values()
		if isinstance(filters, str):
			return [r for r in rows if r["name"] == filters]
		return [r for r in rows if self._match(r, filters or {})]

	# --- frappe API
	def _(self, text):
		return text

	def throw(self, msg, *_a):
		raise _Throw(msg)

	def get_doc(self, doctype, name=None):
		if isinstance(doctype, dict):
			return _Doc(self, **doctype)
		row = {k: v for k, v in self.tables[doctype][name].items() if k != "doctype"}
		return _Doc(self, doctype, **row)

	def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit=None):
		rows = self._rows(doctype, filters)
		if order_by:
			keys = [p.split()[0] for p in order_by.split(",")]
			for key in reversed(keys):
				rows.sort(key=lambda r, k=key: r.get(k) or 0, reverse=True)
		rows = rows[:limit] if limit else rows
		if pluck:
			return [r[pluck] for r in rows]
		return [SimpleNamespace(**r) for r in rows]

	def get_value(self, doctype, filters, fieldname="name", as_dict=False):
		rows = self._rows(doctype, filters)
		if not rows:
			return None
		if isinstance(fieldname, list):
			values = {f: rows[0].get(f) for f in fieldname}
			return SimpleNamespace(**values) if as_dict else tuple(values.values())
		return rows[0].get(fieldname)

	def exists(self, doctype, filters=None):
		return bool(self._rows(doctype, filters))

	def set_value(self, doctype, filters, field, value=None, update_modified=True):
		values = field if isinstance(field, dict) else {field: value}
		for row in self._rows(doctype, filters):
			row.update(values)

	def get_meta(self, doctype):
		return SimpleNamespace(
			get_link_fields=lambda: [],
			get_dynamic_link_fields=lambda: [],
			get_table_fields=lambda: [],
			fields=[],
			get_field=lambda _name: None,
		)

	def count(self, doctype, **filters):
		return len(self._rows(doctype, filters))


def _seed_prompt(fake, doctype="Agent Prompt", **extra):
	fields = {
		"title": "Greeter",
		"prompt_body": "v1 body",
		"version": 1,
		"is_latest": 1,
		"is_active": 1,
		"is_system": 0,
		"visibility": "Private",
		"prompt_group": "P1",
		"creation": 1,
		**extra,
	}
	fake.add(doctype, "P1", **fields)


class PromptVersioningTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe()
		for module in (versioning, lineage):
			patcher = patch.object(module, "frappe", self.fake)
			patcher.start()
			self.addCleanup(patcher.stop)
		for module, name, value in (
			(lineage, "_", self.fake._),
			(versioning, "_", self.fake._),
			(versioning, "cint", lambda v: int(v or 0)),
		):
			patcher = patch.object(module, name, value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _agents(self):
		self.fake.add(
			"Agent",
			"free",
			prompt_mode="Template",
			agent_prompt="P1",
			prompt_version_locked=0,
			template_version_at_attach=1,
		)
		self.fake.add(
			"Agent",
			"locked",
			prompt_mode="Template",
			agent_prompt="P1",
			prompt_version_locked=1,
			template_version_at_attach=1,
		)
		self.fake.add("Skill Prompt", "row1", prompt="P1", usage="System")

	def test_changed_body_creates_next_version_and_moves_links(self):
		_seed_prompt(self.fake)
		self._agents()
		result = versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "v2 body"})

		self.assertTrue(result["versioned"])
		self.assertEqual(result["version"], 2)
		rows = self.fake.tables["Agent Prompt"]
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows["P1"]["is_latest"], 0)
		self.assertEqual(rows["P1"]["prompt_body"], "v1 body")
		new = rows[result["name"]]
		self.assertEqual((new["is_latest"], new["previous_version"], new["prompt_group"]), (1, "P1", "P1"))
		agents = self.fake.tables["Agent"]
		self.assertEqual(agents["free"]["agent_prompt"], result["name"])
		self.assertEqual(agents["free"]["template_version_at_attach"], 2)
		self.assertEqual(agents["locked"]["agent_prompt"], "P1")
		self.assertEqual(self.fake.tables["Skill Prompt"]["row1"]["prompt"], result["name"])

	def test_metadata_only_save_does_not_version(self):
		_seed_prompt(self.fake)
		result = versioning.save_prompt_changes(
			"Agent Prompt", "P1", {"prompt_body": "v1 body", "description": "new", "is_active": 0}
		)
		self.assertFalse(result["versioned"])
		self.assertTrue(result["changed"])
		self.assertEqual(len(self.fake.tables["Agent Prompt"]), 1)
		self.assertEqual(self.fake.tables["Agent Prompt"]["P1"]["description"], "new")
		self.assertEqual(self.fake.tables["Agent Prompt"]["P1"]["is_active"], 0)

	def test_unchanged_save_does_nothing(self):
		_seed_prompt(self.fake, description="d")
		result = versioning.save_prompt_changes(
			"Agent Prompt",
			"P1",
			{"prompt_body": "v1 body", "title": "Greeter", "description": "d", "is_active": True},
		)
		self.assertEqual((result["versioned"], result["changed"]), (False, False))
		self.assertEqual(self.fake.saves, 0)
		self.assertEqual(len(self.fake.tables["Agent Prompt"]), 1)

	def test_old_versions_cannot_be_edited(self):
		_seed_prompt(self.fake, is_latest=0)
		with self.assertRaises(_Throw):
			versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "x"})

	def test_system_prompt_body_not_versioned(self):
		_seed_prompt(self.fake, is_system=1)
		with self.assertRaises(_Throw):
			versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "x"})

	def test_summary_prompts_version_the_same_way(self):
		_seed_prompt(self.fake, doctype="Agent Summary Prompt")
		self.fake.add(
			"Agent",
			"free",
			summary_prompt_mode="Template",
			summary_prompt_template="P1",
			summary_prompt_version_locked=0,
			summary_template_version_at_attach=1,
		)
		self.fake.add(
			"Agent",
			"locked",
			summary_prompt_mode="Template",
			summary_prompt_template="P1",
			summary_prompt_version_locked=1,
			summary_template_version_at_attach=1,
		)
		result = versioning.save_prompt_changes("Agent Summary Prompt", "P1", {"prompt_body": "s2"})
		self.assertEqual(result["version"], 2)
		agents = self.fake.tables["Agent"]
		self.assertEqual(agents["free"]["summary_prompt_template"], result["name"])
		self.assertEqual(agents["locked"]["summary_prompt_template"], "P1")

	def test_permission_checked_before_anything_else(self):
		_seed_prompt(self.fake)
		self.fake.allowed = False
		with self.assertRaises(_Throw):
			versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "x"})
		self.assertEqual(len(self.fake.tables["Agent Prompt"]), 1)
		self.assertEqual(self.fake.tables["Agent Prompt"]["P1"]["is_latest"], 1)

	def test_title_lookup_prefers_latest(self):
		_seed_prompt(self.fake)
		versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "v2 body"})
		latest = next(n for n, r in self.fake.tables["Agent Prompt"].items() if r["is_latest"])
		self.assertNotEqual(latest, "P1")
		self.assertEqual(lineage.find_latest_by_field("Agent Prompt", "title", "Greeter"), latest)
		self.assertEqual(lineage.latest_row("Agent Prompt", "P1"), latest)
		self.assertEqual(lineage.find_seed_target("Agent Prompt", "title", "Greeter"), latest)

	def test_title_lookup_follows_lineage_after_rename(self):
		_seed_prompt(self.fake)
		versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "v2", "title": "Renamed"})
		latest = next(n for n, r in self.fake.tables["Agent Prompt"].items() if r["is_latest"])
		self.assertEqual(lineage.find_latest_by_field("Agent Prompt", "title", "Greeter"), latest)

	def test_importer_resolution_picks_latest(self):
		_seed_prompt(self.fake, slug="greeter")
		versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "v2 body"})
		latest = next(n for n, r in self.fake.tables["Agent Prompt"].items() if r["is_latest"])
		warnings = []
		self.assertEqual(lineage.resolve_prompt_link({"slug": "greeter"}, warnings), latest)
		self.assertEqual(lineage.resolve_prompt_link({"prompt": "Greeter"}, warnings), latest)
		self.assertEqual(lineage.resolve_prompt_link("Greeter", warnings), latest)
		self.assertEqual(warnings, [])
		self.assertIsNone(lineage.resolve_prompt_link({"slug": "missing"}, warnings))
		self.assertEqual(len(warnings), 1)

	def test_upsert_prompt_twice_over_versioned_title_is_idempotent(self):
		from huf.ai.app_seeding import loaders

		_seed_prompt(self.fake, source_app="app")
		versioning.save_prompt_changes("Agent Prompt", "P1", {"prompt_body": "edited"})
		with patch.object(loaders, "frappe", self.fake), patch.object(lineage, "frappe", self.fake):
			for _run in range(2):
				ok, _info = loaders.upsert_prompt(
					{"title": "Greeter", "prompt_body": "seeded"}, "app", "prompts/greeter.json"
				)
				self.assertTrue(ok, _info)

		rows = self.fake.tables["Agent Prompt"]
		self.assertEqual(len(rows), 2)
		self.assertEqual(sum(1 for r in rows.values() if r["title"] == "Greeter"), 2)
		latest = next(r for r in rows.values() if r["is_latest"])
		self.assertEqual(latest["prompt_body"], "seeded")
		self.assertEqual(rows["P1"]["prompt_body"], "v1 body")
		self.assertEqual(rows["P1"]["is_latest"], 0)


class ControllerDoesNotVersionTest(unittest.TestCase):
	def test_doctype_controllers_have_no_auto_version_hook(self):
		import inspect

		from huf.huf.doctype.agent_prompt import agent_prompt
		from huf.huf.doctype.agent_summary_prompt import agent_summary_prompt

		for module in (agent_prompt, agent_summary_prompt):
			source = inspect.getsource(module)
			self.assertNotIn("create_version", source)
			self.assertNotIn("on_update", source)
