# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Shared real-DB / real-Redis harness for the desktop local-capability tests (not a test module).

Same approach as ``test_desktop_local_skills``: real users, real Agent Runs, real leases registered
through the whitelisted endpoints, and a background thread that plays the desktop (polls
``list_pending_desktop_tool_calls`` and answers through ``submit_desktop_tool_event``). Nothing in
the executor path is mocked.
"""

import json
import time
import unittest

import frappe

from huf.ai import desktop_executor as dx
from huf.ai.tests import desktop_test_helpers as h
from huf.ai.tools import desktop_workspace as dw
from huf.ai.tools._registry import (
	DESKTOP_LOCAL_MCP_TOOLS,
	DESKTOP_LOCAL_SKILL_TOOLS,
	DESKTOP_PROCESS_TOOLS,
	DESKTOP_WORKSPACE_TOOLS,
)

BASE_CAPS = ["fs.read", "fs.write", "fs.trash", "exec"]
PROC_CAPS = BASE_CAPS + ["proc"]
MCP_CAPS = BASE_CAPS + ["mcp"]
ALL_CAPS = BASE_CAPS + ["skills.read", "skills.exec", "proc", "mcp", "browser"]
BIDI = "‮⁦​‍﻿"

CATEGORIES = (
	("Desktop Workspace", DESKTOP_WORKSPACE_TOOLS),
	("Desktop Local Skills", DESKTOP_LOCAL_SKILL_TOOLS),
	("Desktop Processes", DESKTOP_PROCESS_TOOLS),
	("Desktop Local MCP", [t for t in DESKTOP_LOCAL_MCP_TOOLS if t["category"] == "Desktop Local MCP"]),
	("Desktop Browser", [t for t in DESKTOP_LOCAL_MCP_TOOLS if t["category"] == "Desktop Browser"]),
)


def catalog(mcp=None, browser=False, skills=None):
	return {"v": 1, "skills": list(skills or []), "mcp": mcp or [], "browser": {"enabled": browser}}


def server(name, tools, agents="any"):
	return {"server": name, "agents": agents, "tools": tools}


def tool(name, description="does a thing", schema=None, source_name=None):
	entry = {
		"name": name,
		"description": description,
		"input_schema": schema if schema is not None else {"type": "object", "properties": {}},
		"annotations": {},
	}
	if source_name:
		entry["source_name"] = source_name
	return entry


def obj_schema(required=(), **props):
	"""Object schema; each keyword is a property whose value is its JSON type."""
	return {
		"type": "object",
		"properties": {k: {"type": v} for k, v in props.items()},
		"required": list(required),
	}


class LocalBase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.user = h.make_user("dxlc")
		cls.other = h.make_user("dxlc2")
		cls._docs = []

	@classmethod
	def tearDownClass(cls):
		h.delete_docs(cls._docs + [("User", cls.user), ("User", cls.other)])

	def setUp(self):
		frappe.set_user(self.user)
		self.exec_id = f"exec-lc-{frappe.generate_hash(length=10)}"

	def tearDown(self):
		frappe.set_user(self.user)
		try:
			h.unregister_desktop_executor(executor_id=self.exec_id)
		except Exception:
			pass
		frappe.set_user("Administrator")

	def register(self, caps=ALL_CAPS):
		frappe.set_user(self.user)
		return h.register_desktop_executor(
			executor_id=self.exec_id,
			protocol_version=1,
			app_version="0.1",
			platform="darwin",
			workspace=h.workspace(),
			capabilities=caps,
		)

	def publish(self, cat):
		frappe.set_user(self.user)
		return h.register_desktop_catalog(executor_id=self.exec_id, catalog=cat)

	def make_run(self, catalog_hash=None, origin=None):
		pin = h.desktop_pin(self.exec_id, self.user)
		if catalog_hash:
			pin["desktop"]["catalog_hash"] = catalog_hash
		if origin:
			pin["desktop"]["origin"] = origin
		run = h.make_run(self.user, pin)
		self._docs.append(("Agent Run", run))
		frappe.set_user(self.user)
		return run

	def kwargs(self, run, **over):
		kw = dict(
			_dx_executor_id=self.exec_id,
			_dx_fingerprint=h.FP,
			_dx_user=self.user,
			agent_run_id=run,
			call_id=f"call-lc-{frappe.generate_hash(length=10)}",
		)
		kw.update(over)
		kw.setdefault("_dx_pin", dw.issue_pin_token(kw["agent_run_id"], kw["_dx_executor_id"], kw["_dx_user"]))
		return kw

	def play(self, run, script):
		"""Wait for a call of ``run`` in list_pending, answer it through submit_desktop_tool_event."""
		seen = []

		def go():
			deadline = time.monotonic() + 15
			req = None
			while time.monotonic() < deadline and req is None:
				for r in h.list_pending_desktop_tool_calls(executor_id=self.exec_id):
					if r["agent_run_id"] == run:
						req = r
				if req is None:
					time.sleep(0.1)
			if req is None:
				raise AssertionError("desktop never saw the call")
			seen.append(req)
			for delay, kind, payload in script:
				time.sleep(delay)
				h.submit_desktop_tool_event(
					call_id=req["call_id"], executor_id=self.exec_id, kind=kind, payload=payload
				)

		return h.run_in_thread(go) + (seen,)

	def finish(self, thread, errors):
		thread.join(30)
		self.assertFalse(thread.is_alive())
		self.assertEqual(errors, [])

	def nothing_was_published(self):
		self.assertEqual(h.list_pending_desktop_tool_calls(executor_id=self.exec_id), [])

	def ok(self, data=None):
		return [(0.05, "ack", {}), (0.05, "result", {"ok": True, "data": data if data is not None else {}})]


class ExposureBase(LocalBase):
	"""Real Agent documents with the registry-synced Agent Tool Function rows attached."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.provider = frappe.db.get_value("AI Provider", {}, "name") or cls._mk_provider()
		cls.model = frappe.db.get_value("AI Model", {"provider": cls.provider}, "name") or cls._mk_model(cls.provider)
		cls.rows = cls._ensure_rows()

	@staticmethod
	def _mk_provider():
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Desktop Local Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	@staticmethod
	def _mk_model(provider):
		doc = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"desktop-local-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	@staticmethod
	def _ensure_rows():
		"""Registry-synced Agent Tool Function rows (created here when the sync has not run)."""
		names = {}
		for category, specs in CATEGORIES:
			if not frappe.db.exists("Agent Tool Type", category):
				frappe.get_doc({"doctype": "Agent Tool Type", "name1": category}).insert(ignore_permissions=True)
			for spec in specs:
				name = frappe.db.get_value("Agent Tool Function", {"tool_name": spec["tool_name"]}, "name")
				if not name:
					props = {}
					for p in spec["parameters"]:
						props[p["fieldname"]] = {"type": p["type"], "description": p.get("description", "")}
						if p["type"] == "array":
							props[p["fieldname"]]["items"] = {"type": "string"}
					doc = frappe.get_doc(
						{
							"doctype": "Agent Tool Function",
							"tool_name": spec["tool_name"],
							"description": spec["description"],
							"tool_type": category,
							"types": "App Provided",
							"function_path": spec["function_path"],
							"params": json.dumps({"type": "object", "properties": props}),
						}
					)
					doc.insert(ignore_permissions=True)
					name = doc.name
				names[spec["tool_name"]] = name
		frappe.db.commit()
		return names

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._agents = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._agents:
			try:
				frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDown()

	def agent(self, tool_names):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"dx-local-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test desktop local capability exposure agent instructions",
				"provider": self.provider,
				"model": self.model,
				"agent_tool": [{"tool": self.rows[n]} for n in tool_names],
			}
		)
		doc.insert(ignore_permissions=True)
		self._agents.append(doc.name)
		return doc

	def ctx(self, catalog_hash=None):
		frappe.set_user(self.user)
		ctx = dx.resolve_desktop_ctx(self.exec_id)
		ctx.pop("catalog_hash", None)
		if catalog_hash:
			ctx["catalog_hash"] = catalog_hash
		return ctx

	def build(self, agent, ctx, only=None):
		from huf.ai.sdk_tools import create_agent_tools

		frappe.set_user(self.user)
		tools = create_agent_tools(agent, desktop_ctx=ctx)
		return {t.name: t for t in tools if only is None or only(t.name)}
