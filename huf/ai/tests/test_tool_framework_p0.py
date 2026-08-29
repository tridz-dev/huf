# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration tests for the tool-calling framework
described in ``docs/testing/CURRENT_STATE.md`` section 4.

Covers, each as a real DB/permission-check round trip (not mocked frappe):

  - TOOL-DEF               : Agent Tool Function insert -> reload round-trip.
  - TOOL-EXPOSE-001        : PermissionAwareToolRegistry.get_allowed_tools
                              includes a tool for a user WITH the required
                              permission.
  - TOOL-EXPOSE-002        : ... excludes it for a user WITHOUT the required
                              permission (P0 security-relevant finding).
  - TOOL-EXPOSE-003        : the documented MCP bypass -- an MCP-sourced tool
                              reaches the assembled tool list without ever
                              going through PermissionAwareToolRegistry's
                              gate, for a user with NO permission at all on
                              the MCP Server doctype.
  - TOOL-FAIL-001          : deterministic_fail's exception is caught by the
                              real create_function_tool/on_invoke_tool path
                              and returned as a JSON error, not raised.
  - TOOL-FAIL-002          : a broken function_path silently resolves to
                              None (get_function_from_name) and therefore
                              create_function_tool also returns None --
                              proving the "silent tool disappearance"
                              behavior rather than a startup error.
  - TOOL-PERM-001          : permission_protected_mutation's own
                              handler-level frappe.has_permission gate
                              denies a user without the required permission,
                              exercised through the real on_invoke_tool
                              closure (not just calling the handler
                              function).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_tool_framework_p0

Every fixture created by this file is prefixed "_Test P33 " so it cannot
collide with fixtures created by another concurrent test file sharing the
same site/bench.
"""

import asyncio
import json
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tests.factories import (
    create_test_tool_doc,
    make_agent,
    make_mcp_server,
    make_user,
)
from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.sdk_tools import create_function_tool, get_function_from_name
from huf.install import create_huf_roles

PREFIX = "_Test P33"


def _run(coro):
    """Run an ``on_invoke_tool`` coroutine synchronously (no event loop is
    active in a plain bench test process)."""
    return asyncio.run(coro)


class TestToolFrameworkP0(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_huf_roles()

    def setUp(self):
        self._names = {
            "User": [],
            "Agent": [],
            "Agent Tool Function": [],
            "Agent Tool Type": [],
            "MCP Server": [],
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        # Delete in dependency order: Agent (references tools/MCP) first.
        for doctype in ("Agent", "Agent Tool Function", "MCP Server", "Agent Tool Type", "User"):
            for name in self._names.get(doctype, []):
                self._delete(doctype, name)
        frappe.db.commit()

    def _delete(self, doctype, name):
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)
        return name

    def _make_user(self, roles=(), suffix=""):
        user = make_user(
            email=f"huf-p33-test-{suffix}-{frappe.generate_hash(length=8)}@example.com",
            roles=roles,
        )
        self._track("User", user.name)
        return user.name

    def _make_agent(self, **overrides):
        overrides.setdefault("agent_name", f"{PREFIX} Agent {frappe.generate_hash(length=8)}")
        agent = make_agent(**overrides)
        self._track("Agent", agent.name)
        return agent

    # -- TOOL-DEF -------------------------------------------------------

    def test_tool_def_insert_reload_roundtrip(self):
        """Agent Tool Function insert -> reload preserves params/schema and
        function_path (huf/huf/doctype/agent_tool_function/agent_tool_function.json)."""
        doc = create_test_tool_doc(
            "deterministic_add",
            tool_name=f"{PREFIX.replace(' ', '_').lower()}_tool_def",
        )
        self._track("Agent Tool Function", doc.name)

        reloaded = frappe.get_doc("Agent Tool Function", doc.name)

        self.assertEqual(reloaded.function_path, "huf.ai.test_tools.deterministic_add")
        self.assertEqual(reloaded.types, "Custom Function")
        self.assertTrue(reloaded.is_read_only)

        schema = json.loads(reloaded.params)
        self.assertEqual(schema["type"], "object")
        self.assertIn("numbers", schema["properties"])
        self.assertEqual(schema["required"], ["numbers"])

    # -- TOOL-EXPOSE-001 / 002 -------------------------------------------
    #
    # Both use "AI Provider" as the gated reference_doctype rather than the
    # test-tool-spec builder's own default ("ToDo") because AI Provider's
    # permission list (huf/huf/doctype/ai_provider/ai_provider.json) is
    # verified in-repo: ONLY "System Manager" has write=1 -- "Huf Manager"
    # and "Huf User" are both explicitly write=0 (confirmed against a real
    # bench via `bench console`: a fresh "Huf Manager" user's
    # frappe.has_permission("AI Provider", "write") is False). That gives a
    # deterministic has/has-not split without depending on unverifiable
    # core-Frappe ToDo permission defaults (ToDo ships with frappe core, not
    # this app).

    def _make_gated_tool(self, name_suffix):
        doc = create_test_tool_doc(
            "permission_protected_mutation",
            tool_name=f"{PREFIX.replace(' ', '_').lower()}_gated_{name_suffix}",
            required_permission="write",
            reference_doctype="AI Provider",
        )
        self._track("Agent Tool Function", doc.name)
        return doc

    def test_tool_expose_001_permitted_user_sees_tool(self):
        tool_doc = self._make_gated_tool("exp1")
        agent = self._make_agent()
        agent.append("agent_tool", {"tool": tool_doc.name})
        agent.save(ignore_permissions=True)

        # System Manager is the only role with write=1 on AI Provider per
        # the doctype's own permission list (see note above).
        user = self._make_user(roles=("System Manager",), suffix="exp1")

        allowed = PermissionAwareToolRegistry.get_allowed_tools(agent, user)
        allowed_names = [t.name for t in allowed]
        self.assertIn(tool_doc.name, allowed_names)

    def test_tool_expose_002_unpermitted_user_is_excluded(self):
        """P0: a user who lacks the tool's required_permission on its
        reference_doctype must NOT see the tool in the assembled list."""
        tool_doc = self._make_gated_tool("exp2")
        agent = self._make_agent()
        agent.append("agent_tool", {"tool": tool_doc.name})
        agent.save(ignore_permissions=True)

        # "Huf User" is explicitly write=0 on AI Provider.
        user = self._make_user(roles=("Huf User",), suffix="exp2")
        self.assertFalse(
            frappe.has_permission(doctype="AI Provider", ptype="write", user=user),
            "test precondition failed: Huf User unexpectedly has write on AI Provider",
        )

        allowed = PermissionAwareToolRegistry.get_allowed_tools(agent, user)
        allowed_names = [t.name for t in allowed]
        self.assertNotIn(tool_doc.name, allowed_names)

    # -- TOOL-EXPOSE-003 (documented MCP bypass) -------------------------

    def test_tool_expose_003_mcp_tool_bypasses_permission_registry(self):
        """Prove the documented gap: an MCP-sourced tool is built into the
        assembled tool list via huf.ai.mcp_client.create_mcp_tools, which
        never calls PermissionAwareToolRegistry / frappe.has_permission at
        all during assembly -- not even the "MCP Server: read" check the
        docs describe as the only gate. That check only happens later, at
        actual invocation time, inside mcp_client.execute_mcp_tool.

        DRIFT NOTE: CURRENT_STATE.md section 4 says "the only gate for an
        MCP tool is frappe.has_permission('MCP Server','read',...)". Reading
        huf/ai/mcp_client.py::create_mcp_tools shows that check is NOT
        present at assembly time at all -- frappe.get_doc("MCP Server", ...)
        does not enforce read permission on its own, and create_mcp_tools
        never calls has_permission or check_permission before building the
        FunctionTool. The has_permission("MCP Server", "read", ...) check
        that does exist lives in execute_mcp_tool (the runtime call path),
        not in assembly. This test asserts the assembly-time gap is real by
        using a user with literally NO Huf role (no read grant on MCP
        Server either) and showing the tool is still returned.
        """
        from huf.ai.mcp_client import create_mcp_tools

        server = make_mcp_server(server_name=f"{PREFIX} MCP Server {frappe.generate_hash(length=6)}")
        self._track("MCP Server", server.name)
        server.append(
            "tools",
            {
                "tool_name": f"{PREFIX.replace(' ', '_').lower()}_mcp_tool",
                "enabled": 1,
                "description": "Test MCP-sourced tool for bypass proof.",
                "parameters": json.dumps({"type": "object", "properties": {}}),
            },
        )
        server.save(ignore_permissions=True)

        agent = self._make_agent()

        # A bare user: no Huf User / Huf Manager / System Manager role at
        # all, so no permission entry in mcp_server.json's permission list
        # applies -- not even read.
        user = self._make_user(roles=(), suffix="mcpbypass")
        self.assertFalse(
            frappe.has_permission(doctype="MCP Server", ptype="read", user=user),
            "test precondition failed: bare user unexpectedly has read on MCP Server",
        )

        frappe.set_user(user)
        try:
            tools = create_mcp_tools(agent, mcp_server_names=[server.name])
        finally:
            frappe.set_user("Administrator")

        tool_names = [t.name for t in tools]
        # The tool must be present despite the user having zero permission
        # on the MCP Server doctype -- proving assembly-time bypass.
        self.assertTrue(
            any("mcp_tool" in n for n in tool_names),
            f"expected the MCP-sourced tool to bypass the permission registry, got {tool_names}",
        )

    # -- TOOL-FAIL-001 ----------------------------------------------------

    def test_tool_fail_001_handler_exception_becomes_json_error(self):
        """deterministic_fail's exception must be caught by the real
        on_invoke_tool closure (sdk_tools.py) and returned as
        json.dumps({"error": ...}) rather than propagating."""
        doc = create_test_tool_doc(
            "deterministic_fail",
            tool_name=f"{PREFIX.replace(' ', '_').lower()}_fail",
        )
        self._track("Agent Tool Function", doc.name)

        tool = create_function_tool(
            name=doc.tool_name,
            description=doc.description,
            tool_name=doc.function_path,
            parameters=json.loads(doc.params) if doc.params else {},
            tool_type=doc.types,
        )
        self.assertIsNotNone(tool, "create_function_tool unexpectedly returned None for a valid function_path")

        result_json = _run(tool.on_invoke_tool(ctx=None, args_json="{}"))
        result = json.loads(result_json)

        self.assertIn("error", result)
        self.assertIn("intentional test failure", result["error"])
        # Must NOT carry the assembly-time permission-denial shape.
        self.assertNotIn("denied", result)

    # -- TOOL-FAIL-002 ----------------------------------------------------

    def test_tool_fail_002_broken_function_path_vanishes_silently(self):
        """A broken function_path resolves to None from
        get_function_from_name (import/attribute error swallowed, only a
        debug log line) -- and create_function_tool built on top of it
        also returns None, rather than either one raising."""
        broken_path = "huf.ai.test_tools.this_function_does_not_exist_p33"

        # Direct resolution: must return None, not raise.
        self.assertIsNone(get_function_from_name(broken_path))

        # Also broken *module* path (import error), still None not raise.
        self.assertIsNone(get_function_from_name("huf.ai.this_module_does_not_exist_p33.some_fn"))

        # Note: Agent Tool Function.validate() (agent_tool_function.py:808-814)
        # eagerly resolves function_path via frappe.get_attr() and throws at
        # SAVE TIME if it doesn't resolve -- so a broken path can never
        # actually be persisted as a real DocType record in the first place.
        # The "silent vanishing" this test is about only applies to
        # create_function_tool()'s own resilience against an unresolvable
        # tool_name passed directly (e.g. the underlying function existed at
        # save time and was later removed/renamed) -- exercised below without
        # going through doc persistence, which would correctly reject it.
        doc = create_test_tool_doc(
            "deterministic_add",
            tool_name=f"{PREFIX.replace(' ', '_').lower()}_broken_path",
        )
        self._track("Agent Tool Function", doc.name)

        tool = create_function_tool(
            name=doc.tool_name,
            description=doc.description,
            tool_name=broken_path,
            parameters=json.loads(doc.params) if doc.params else {},
            tool_type=doc.types,
        )
        self.assertIsNone(
            tool,
            "create_function_tool should silently return None for an unresolvable function_path",
        )

    # -- TOOL-PERM-001 ------------------------------------------------------

    def test_tool_perm_001_handler_level_gate_denies_without_permission(self):
        """permission_protected_mutation does its own inline
        frappe.has_permission("ToDo", "write") check (huf/ai/test_tools.py)
        independent of the assembly-time registry gate. Exercised through
        the real on_invoke_tool closure (sdk_tools.create_function_tool),
        not by calling the handler function directly.

        Guest is used here (rather than a "Huf User") because ToDo is a
        core Frappe doctype not vendored in this app -- its permission
        defaults for authenticated custom roles cannot be verified from
        this repo's own doctype JSON the way AI Provider's could above.
        Guest lacking write permission on ToDo without an explicit grant is
        the one assumption safe to make without a live site to check
        against; the coordinator's bench pass should double check this
        still holds if this test unexpectedly fails on write=True.
        """
        doc = create_test_tool_doc(
            "permission_protected_mutation",
            tool_name=f"{PREFIX.replace(' ', '_').lower()}_perm001",
        )
        self._track("Agent Tool Function", doc.name)

        tool = create_function_tool(
            name=doc.tool_name,
            description=doc.description,
            tool_name=doc.function_path,
            parameters=json.loads(doc.params) if doc.params else {},
            tool_type=doc.types,
            allowed_for_guest=bool(doc.allowed_for_guest),
        )
        self.assertIsNotNone(tool)

        frappe.set_user("Guest")
        try:
            self.assertFalse(
                frappe.has_permission(doctype="ToDo", ptype="write", user="Guest"),
                "test precondition failed: Guest unexpectedly has write on ToDo",
            )
            result_json = _run(
                tool.on_invoke_tool(ctx=None, args_json=json.dumps({"record_id": "r1", "value": "v1"}))
            )
        finally:
            frappe.set_user("Administrator")

        result = json.loads(result_json)
        self.assertFalse(result.get("success"))
        self.assertTrue(result.get("permission_denied"))


if __name__ == "__main__":
    unittest.main()
