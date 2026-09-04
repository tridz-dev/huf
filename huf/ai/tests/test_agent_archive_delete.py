# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unit tests for the archive/delete-cascade additions to
huf.huf.doctype.agent.agent (WP-R4 ST-R4.4):

- archive_agent(): a plain field update (frappe.db.set_value), never routed
  through on_trash / delete_doc.
- delete_agent_cascade(): System-Manager-only, deletes children (Agent
  Message, Agent Conversation, Agent Run) before calling frappe.delete_doc
  on the Agent itself.
- get_permission_query_conditions(): excludes disabled (archived) agents
  from default Agent list views, the same way it already excludes
  is_system agents.

These are standalone unit tests against the module loaded directly from
its file path — `huf.huf.doctype.agent.agent` pulls in heavy sibling
modules (agent_integration, orchestration, prompt_cache_capabilities) that
are not needed to exercise archive_agent/delete_agent_cascade/PQC, so they
are stubbed out here the same way `huf/ai/tests/_stub_env.py` stubs
frappe/litellm/agents for the rest of this standalone test suite.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_archive_delete
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch

from huf.ai.tests import _stub_env

_stub_env.install()


def _make_module(name):
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _stub_agent_module_dependencies():
    """Stub the heavy sibling modules huf/huf/doctype/agent/agent.py imports
    at module load time, so loading it here doesn't require litellm/openai
    agents SDK/orchestration machinery to actually run.
    """
    frappe = sys.modules.get("frappe")
    is_real_frappe = frappe is not None and not isinstance(frappe, MagicMock)
    if frappe is not None and not is_real_frappe:
        frappe_model = _make_module("frappe.model")
        frappe_model.__path__ = ["frappe/model"]

        frappe_model_document = _make_module("frappe.model.document")

        class Document:
            pass

        frappe_model_document.Document = Document
        frappe_model.document = frappe_model_document
        frappe.model = frappe_model

        # `@frappe.whitelist()` / `@frappe.whitelist` must be identity
        # decorators — a bare MagicMock would swallow the real function and
        # replace it with a Mock, so the tests below would no longer be
        # exercising the actual archive_agent/delete_agent_cascade bodies.
        def _whitelist(*args, **kwargs):
            if args and callable(args[0]) and not kwargs:
                return args[0]
            return lambda f: f

        frappe.whitelist = _whitelist
        frappe._ = lambda s, *a, **kw: s
        frappe.PermissionError = type("PermissionError", (Exception,), {})

        def _throw(msg, exc=Exception, *a, **kw):
            raise exc(msg)

        frappe.throw = MagicMock(side_effect=_throw)
        frappe.db = MagicMock(name="frappe.db")
        frappe.session = MagicMock(name="frappe.session")
        frappe.get_roles = MagicMock(return_value=[])
        frappe.get_all = MagicMock(return_value=[])
        frappe.get_doc = MagicMock()
        frappe.delete_doc = MagicMock()
        frappe.logger = MagicMock(return_value=MagicMock())
        frappe.generate_hash = MagicMock(return_value="x" * 32)

    agent_hooks = _make_module("huf.ai.agent_hooks")
    agent_hooks.clear_doc_event_agents_cache = MagicMock(name="clear_doc_event_agents_cache")

    agent_integration = _make_module("huf.ai.agent_integration")
    agent_integration.run_agent_sync = MagicMock(name="run_agent_sync")

    prompt_cache_capabilities = _make_module("huf.ai.prompt_cache_capabilities")
    prompt_cache_capabilities.model_supports_prompt_caching = MagicMock(
        name="model_supports_prompt_caching", return_value=False
    )

    orchestration_pkg = _make_module("huf.ai.orchestration")
    orchestration_pkg.__path__ = ["huf/ai/orchestration"]

    planning = _make_module("huf.ai.orchestration.planning")
    planning.run_planning = MagicMock(name="run_planning")

    orchestrator = _make_module("huf.ai.orchestration.orchestrator")
    orchestrator.parse_plan_steps = MagicMock(name="parse_plan_steps")
    orchestrator.create_orchestration = MagicMock(name="create_orchestration")

    huf_permissions = _make_module("huf.permissions")
    if not hasattr(huf_permissions, "has_capability"):
        huf_permissions.has_capability = MagicMock(name="has_capability", return_value=False)


def _load_agent_module():
    """Load huf/huf/doctype/agent/agent.py directly from its file path.

    Avoids needing the full huf.huf.doctype.agent package hierarchy to
    exist as importable packages (only huf.ai.* is stubbed by _stub_env) —
    imports *inside* the loaded file resolve normally against sys.modules
    regardless of what module name we register it under.
    """
    _stub_agent_module_dependencies()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    file_path = os.path.join(repo_root, "huf", "huf", "doctype", "agent", "agent.py")
    if not os.path.exists(file_path):
        # Fall back: tests dir is huf/ai/tests, so repo_root above is huf/.
        file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "huf",
            "doctype",
            "agent",
            "agent.py",
        )

    spec = importlib.util.spec_from_file_location("agent_under_test", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_module = _load_agent_module()


class TestArchiveAgent(unittest.TestCase):
    def setUp(self):
        self.frappe = agent_module.frappe

    def test_archive_agent_sets_disabled_via_plain_field_update(self):
        agent_doc = MagicMock(owner="owner@example.com")
        with patch.object(self.frappe, "get_doc", return_value=agent_doc), patch.object(
            self.frappe, "session", MagicMock(user="owner@example.com")
        ), patch.object(self.frappe.db, "set_value") as mock_set_value, patch(
            "huf.permissions.has_capability", return_value=False
        ):
            agent_module.archive_agent("Some Agent")

        mock_set_value.assert_called_once_with("Agent", "Some Agent", "disabled", 1)
        agent_module.clear_doc_event_agents_cache.assert_called()

    def test_archive_agent_denies_user_without_capability_or_ownership(self):
        agent_doc = MagicMock(owner="owner@example.com")
        with patch.object(self.frappe, "get_doc", return_value=agent_doc), patch.object(
            self.frappe, "session", MagicMock(user="other@example.com")
        ), patch.object(self.frappe.db, "set_value") as mock_set_value, patch(
            "huf.permissions.has_capability", return_value=False
        ), patch.object(self.frappe, "throw", side_effect=Exception("PermissionError")) as mock_throw:
            with self.assertRaises(Exception):
                agent_module.archive_agent("Some Agent")
        mock_throw.assert_called_once()
        mock_set_value.assert_not_called()

    def test_pqc_excludes_disabled_agents_for_privileged_user(self):
        with patch.object(self.frappe, "get_roles", return_value=[]), patch(
            "huf.permissions.has_capability", return_value=True
        ):
            condition = agent_module.get_permission_query_conditions("someone@example.com")
        self.assertIn("`tabAgent`.disabled = 0", condition)

    def test_pqc_excludes_disabled_agents_for_regular_user(self):
        with patch.object(self.frappe, "get_roles", return_value=["Some Role"]), patch(
            "huf.permissions.has_capability", return_value=False
        ):
            condition = agent_module.get_permission_query_conditions("someone@example.com")
        self.assertIn("`tabAgent`.disabled = 0", condition)

    def test_pqc_returns_none_for_system_manager(self):
        with patch.object(self.frappe, "get_roles", return_value=["System Manager"]):
            condition = agent_module.get_permission_query_conditions("admin@example.com")
        self.assertIsNone(condition)


class TestDeleteAgentCascade(unittest.TestCase):
    def setUp(self):
        self.frappe = agent_module.frappe

    def test_raises_permission_error_for_non_system_manager(self):
        with patch.object(self.frappe, "get_roles", return_value=["Huf User"]), patch.object(
            self.frappe, "session", MagicMock(user="user@example.com")
        ), patch.object(self.frappe, "PermissionError", Exception), patch.object(
            self.frappe, "throw", side_effect=Exception("PermissionError")
        ) as mock_throw, patch.object(self.frappe, "delete_doc") as mock_delete_doc:
            with self.assertRaises(Exception):
                agent_module.delete_agent_cascade("Some Agent")
        mock_throw.assert_called_once()
        mock_delete_doc.assert_not_called()

    def test_deletes_children_before_parent_in_order(self):
        call_order = []

        def record_get_all(*args, **kwargs):
            call_order.append(("get_all",) + args)
            return ["Conv-1", "Conv-2"]

        def record_db_delete(*args, **kwargs):
            call_order.append(("db.delete",) + args)

        def record_delete_doc(*args, **kwargs):
            call_order.append(("delete_doc",) + args)

        with patch.object(self.frappe, "get_roles", return_value=["System Manager"]), patch.object(
            self.frappe, "session", MagicMock(user="admin@example.com")
        ), patch.object(self.frappe, "get_all", side_effect=record_get_all), patch.object(
            self.frappe.db, "delete", side_effect=record_db_delete
        ), patch.object(
            self.frappe, "delete_doc", side_effect=record_delete_doc
        ), patch.object(
            self.frappe, "logger", return_value=MagicMock()
        ):
            agent_module.delete_agent_cascade("Some Agent")

        # Order must be: find conversations, delete messages, delete
        # conversations, delete runs, THEN delete the agent itself.
        kinds = [c[0] for c in call_order]
        self.assertEqual(
            kinds,
            ["get_all", "db.delete", "db.delete", "db.delete", "delete_doc"],
        )
        self.assertEqual(call_order[1], ("db.delete", "Agent Message", {"conversation": ("in", ["Conv-1", "Conv-2"])}))
        self.assertEqual(call_order[2], ("db.delete", "Agent Conversation", {"name": ("in", ["Conv-1", "Conv-2"])}))
        self.assertEqual(call_order[3], ("db.delete", "Agent Run", {"agent": "Some Agent"}))
        self.assertEqual(call_order[4], ("delete_doc", "Agent", "Some Agent"))

    def test_agent_with_no_linked_runs_still_deletes_via_plain_delete_doc(self):
        """Regression: an agent with no conversations at all must skip the
        Agent Message/Agent Conversation deletes (empty pluck result) and
        still reach frappe.delete_doc unchanged.
        """
        with patch.object(self.frappe, "get_roles", return_value=["System Manager"]), patch.object(
            self.frappe, "session", MagicMock(user="admin@example.com")
        ), patch.object(self.frappe, "get_all", return_value=[]), patch.object(
            self.frappe.db, "delete"
        ) as mock_db_delete, patch.object(
            self.frappe, "delete_doc"
        ) as mock_delete_doc, patch.object(
            self.frappe, "logger", return_value=MagicMock()
        ):
            agent_module.delete_agent_cascade("Lonely Agent")

        # No conversations found -> Agent Message/Agent Conversation deletes
        # are skipped; only Agent Run delete plus the final delete_doc run.
        mock_db_delete.assert_called_once_with("Agent Run", {"agent": "Lonely Agent"})
        mock_delete_doc.assert_called_once_with("Agent", "Lonely Agent")


if __name__ == "__main__":
    unittest.main()
