"""Pure-Python unit tests for memory permission gates and tool auto-wiring.

These tests mock Frappe so they can run outside a live site context.
Run with: python3 -m pytest huf/ai/tests/test_memory_tools.py -v
"""

import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Build a mock frappe package for the permission-gate tests below.
_mock_frappe = MagicMock()
_mock_frappe.session.user = "test_user@example.com"
_mock_frappe.get_roles.return_value = {"Huf User"}
_mock_frappe.local.site = "test_site"
_mock_frappe.db.exists.return_value = False
_mock_frappe.db.get_value.return_value = None
_mock_frappe.get_doc.return_value = MagicMock()
_mock_frappe.throw.side_effect = Exception("frappe.throw")
_mock_frappe.log_error = MagicMock()

_mock_frappe_utils = MagicMock()
_mock_frappe_utils.now_datetime.return_value = datetime(2026, 7, 4, 11, 0, 0)
_mock_frappe.utils = _mock_frappe_utils

_mock_frappe_background_jobs = MagicMock()
_mock_frappe_file_manager = MagicMock()
_mock_frappe.client = MagicMock()

_mock_agents = MagicMock()
_mock_agents.FunctionTool = MagicMock()


def _has_real_frappe() -> bool:
    """True when running inside a Frappe environment (e.g. bench run-tests)."""
    try:
        import frappe as real_frappe
    except ImportError:
        return False
    # A MagicMock already injected into sys.modules has no string __file__.
    return isinstance(getattr(real_frappe, "__file__", None), str)


if not _has_real_frappe():
    # Standalone pytest (no Frappe installed): inject mocks so the huf imports
    # below work at all. Never do this under bench — replacing
    # sys.modules["frappe"] at import time leaks into every other test module
    # discovered in the same run and breaks their DB work with MagicMocks.
    sys.modules["frappe"] = _mock_frappe
    sys.modules["frappe.utils"] = _mock_frappe_utils
    sys.modules["frappe.utils.background_jobs"] = _mock_frappe_background_jobs
    sys.modules["frappe.utils.file_manager"] = _mock_frappe_file_manager
    sys.modules["frappe.client"] = _mock_frappe.client
    sys.modules["agents"] = _mock_agents

from huf.ai import memory_tools, sdk_tools
from huf.ai.sdk_tools import create_agent_tools


class _MockFrappeTestCase(unittest.TestCase):
    """Point the modules under test at the mock frappe for each test.

    Under bench the huf modules are already imported with the real frappe
    module bound, so swap the module-global reference per test and restore it
    afterwards. In standalone mode the modules were imported against the mock
    already, making this a harmless no-op.
    """

    def setUp(self):
        for module in (memory_tools, sdk_tools):
            patcher = patch.object(module, "frappe", _mock_frappe)
            patcher.start()
            self.addCleanup(patcher.stop)


class TestCanWriteMemory(_MockFrappeTestCase):
    """Unit tests for _can_write_memory policy + role gates (B3 fix)."""

    def setUp(self):
        super().setUp()
        # Reset shared mock state
        _mock_frappe.session.user = "test_user@example.com"
        _mock_frappe.get_roles.return_value = {"Huf User"}
        memory_tools.MANAGER_ROLES = {"System Manager", "Huf Manager"}

    def _make_policy(self, **kwargs):
        defaults = {
            "allow_user_scope_write": True,
            "allow_agent_scope_write": True,
            "allow_role_scope_write": True,
            "allow_site_scope_write": True,
            "allow_agent_write": True,
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)

    @patch.object(memory_tools, "_is_manager")
    def test_policy_switch_off_denies_manager(self, mock_is_manager):
        """B3 fix: disabled policy write switch denies even a manager."""
        mock_is_manager.return_value = True
        policy = self._make_policy(allow_user_scope_write=False)
        self.assertFalse(
            memory_tools._can_write_memory("User", "test_user@example.com", policy=policy)
        )

    @patch.object(memory_tools, "_is_manager")
    def test_policy_switch_on_plus_manager_allows(self, mock_is_manager):
        """B3 fix: enabled switch + manager allows the write."""
        mock_is_manager.return_value = True
        policy = self._make_policy(allow_user_scope_write=True)
        self.assertTrue(
            memory_tools._can_write_memory("User", "test_user@example.com", policy=policy)
        )

    @patch.object(memory_tools, "_is_manager")
    def test_non_manager_blocked_for_role_site_global_even_with_switches_on(
        self, mock_is_manager
    ):
        """Non-managers cannot write Role/Site/Global scopes regardless of switches."""
        mock_is_manager.return_value = False
        policy = self._make_policy(
            allow_role_scope_write=True, allow_site_scope_write=True
        )
        for scope in ("Role", "Site", "Global", "Workspace"):
            with self.subTest(scope=scope):
                self.assertFalse(
                    memory_tools._can_write_memory(scope, "some-key", policy=policy)
                )

    @patch.object(memory_tools, "_is_manager")
    def test_user_scope_requires_scope_key_matches_session_user(self, mock_is_manager):
        """User scope write requires scope_key == session user."""
        mock_is_manager.return_value = False
        _mock_frappe.session.user = "alice@example.com"
        policy = self._make_policy(allow_user_scope_write=True)
        self.assertTrue(
            memory_tools._can_write_memory("User", "alice@example.com", policy=policy)
        )
        self.assertFalse(
            memory_tools._can_write_memory("User", "bob@example.com", policy=policy)
        )

    @patch.object(memory_tools, "_is_manager")
    def test_allow_agent_write_zero_denies(self, mock_is_manager):
        """allow_agent_write=0 denies any write even if scope switch is on."""
        mock_is_manager.return_value = True
        policy = self._make_policy(
            allow_user_scope_write=True, allow_agent_write=False
        )
        self.assertFalse(
            memory_tools._can_write_memory("User", "test_user@example.com", policy=policy)
        )

    def test_guest_always_blocked(self):
        """Guest users are always blocked from writing memory."""
        _mock_frappe.session.user = "Guest"
        policy = self._make_policy()
        self.assertFalse(
            memory_tools._can_write_memory("User", "Guest", policy=policy)
        )


class TestCanReadMemory(_MockFrappeTestCase):
    """Unit tests for _can_read_memory, especially conversation ownership."""

    def setUp(self):
        super().setUp()
        _mock_frappe.session.user = "test_user@example.com"
        _mock_frappe.get_roles.return_value = {"Huf User"}

    @patch.object(memory_tools, "_owns_conversation")
    @patch.object(memory_tools, "_is_manager")
    def test_conversation_scope_requires_ownership(
        self, mock_is_manager, mock_owns_conversation
    ):
        """Conversation-scoped reads require the user to own the conversation."""
        mock_is_manager.return_value = False
        conv_id = "conv-123"

        # Owner
        mock_owns_conversation.return_value = True
        row = {
            "scope_type": "Conversation",
            "scope_key": conv_id,
            "visibility": "Private",
        }
        self.assertTrue(
            memory_tools._can_read_memory(row, conversation_id=conv_id)
        )

        # Non-owner
        mock_owns_conversation.return_value = False
        self.assertFalse(
            memory_tools._can_read_memory(row, conversation_id=conv_id)
        )

    @patch.object(memory_tools, "_is_manager")
    def test_user_scope_requires_scope_key_match(self, mock_is_manager):
        """User-scoped reads require scope_key == session user."""
        mock_is_manager.return_value = False
        _mock_frappe.session.user = "alice@example.com"
        row = {"scope_type": "User", "scope_key": "alice@example.com"}
        self.assertTrue(memory_tools._can_read_memory(row))

        row["scope_key"] = "bob@example.com"
        self.assertFalse(memory_tools._can_read_memory(row))

    def test_manager_can_read_anything(self):
        """Managers bypass per-row read checks."""
        _mock_frappe.get_roles.return_value = {"Huf Manager"}
        row = {"scope_type": "Global", "scope_key": "global", "visibility": "Global"}
        self.assertTrue(memory_tools._can_read_memory(row))


class TestMemoryToolAutoWiring(_MockFrappeTestCase):
    """Unit tests for B2 auto-wiring of memory tools from Agent flags."""

    def _make_agent(self, **kwargs):
        defaults = {
            "enable_memory": True,
            "enable_memory_search_tool": True,
            "enable_memory_write_tool": True,
            "agent_tool": [],
            "agent_mcp_server": [],
        }
        defaults.update(kwargs)
        agent = MagicMock()
        for k, v in defaults.items():
            setattr(agent, k, v)
        return agent

    def _make_tool_doc(self, tool_name):
        doc = MagicMock()
        doc.tool_name = tool_name
        doc.tool_type = "Memory"
        doc.types = "Save Memory Record" if "save" in tool_name else "Search Memory Records" if "search" in tool_name else "Get Memory Record" if "get" in tool_name else "Archive Memory Record"
        doc.name = tool_name.upper()
        doc.params = '{}'
        doc.description = f"Mock {tool_name}"
        doc.reference_doctype = None
        doc.function_path = f"huf.ai.memory_tools.handle_{tool_name}"
        doc.allowed_for_guest = False
        doc.is_read_only = False
        doc.required_permission = None
        return doc

    @patch("huf.ai.sdk_tools.create_function_tool")
    @patch("huf.ai.sdk_tools.PermissionAwareToolRegistry.get_allowed_tools")
    @patch.object(_mock_frappe.db, "exists")
    @patch.object(_mock_frappe, "get_doc")
    def test_auto_wires_search_and_write_tools_when_flags_on(
        self, mock_get_doc, mock_exists, mock_get_allowed, mock_create_tool
    ):
        """When memory flags are on, search/get and save/archive tools are added."""
        mock_get_allowed.return_value = []
        mock_exists.return_value = True
        mock_get_doc.side_effect = lambda _dt, _filt: self._make_tool_doc(
            _filt.get("tool_name") if isinstance(_filt, dict) else _filt
        )
        mock_create_tool.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name"))

        agent = self._make_agent()
        create_agent_tools(agent)

        created_names = [
            (call.args[0] if call.args else call.kwargs.get("name"))
            for call in mock_create_tool.call_args_list
        ]
        self.assertIn("search_memory_records", created_names)
        self.assertIn("get_memory_record", created_names)
        self.assertIn("save_memory_record", created_names)
        self.assertIn("archive_memory_record", created_names)

    @patch("huf.ai.sdk_tools.create_function_tool")
    @patch("huf.ai.sdk_tools.PermissionAwareToolRegistry.get_allowed_tools")
    @patch.object(_mock_frappe.db, "exists")
    def test_dedupes_tools_already_in_agent_child_table(
        self, mock_exists, mock_get_allowed, mock_create_tool
    ):
        """Memory tools already present via agent_tool child table are not duplicated."""
        existing_doc = self._make_tool_doc("search_memory_records")
        mock_get_allowed.return_value = [existing_doc]
        mock_exists.return_value = True
        mock_create_tool.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name"))

        agent = self._make_agent()
        create_agent_tools(agent)

        created_names = [
            (call.args[0] if call.args else call.kwargs.get("name"))
            for call in mock_create_tool.call_args_list
        ]
        self.assertEqual(created_names.count("search_memory_records"), 1)

    @patch("huf.ai.sdk_tools.create_function_tool")
    @patch("huf.ai.sdk_tools.PermissionAwareToolRegistry.get_allowed_tools")
    def test_no_memory_tools_when_enable_memory_is_off(
        self, mock_get_allowed, mock_create_tool
    ):
        """When enable_memory is False, no memory tools are auto-wired."""
        mock_get_allowed.return_value = []
        mock_create_tool.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name"))

        agent = self._make_agent(enable_memory=False)
        create_agent_tools(agent)

        created_names = [
            (call.args[0] if call.args else call.kwargs.get("name"))
            for call in mock_create_tool.call_args_list
        ]
        self.assertNotIn("search_memory_records", created_names)
        self.assertNotIn("save_memory_record", created_names)


if __name__ == "__main__":
    unittest.main()
