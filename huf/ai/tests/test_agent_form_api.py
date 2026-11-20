# Track-Item: AF-1
"""Stubbed unit tests for huf.ai.agent.agent_form_api (no real bench).

frappe is replaced with a MagicMock for the duration of each module load; the
module under test is loaded from its file path.  ``apply_draft_overrides`` is
lives in agent_form_api so integration.py (too heavy to import) can share it.
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # .../huf


class _PermErr(Exception):
    pass


class _ValErr(Exception):
    pass


def _fake_frappe(roles=("System Manager",), user="u@x.com"):
    f = types.SimpleNamespace()
    f._ = lambda s, *a, **k: s
    f.PermissionError = _PermErr
    f.ValidationError = _ValErr

    def _throw(msg, exc=Exception, *a, **k):
        raise exc(msg)

    f.throw = _throw
    f.session = types.SimpleNamespace(user=user)
    f.get_roles = lambda u=None: list(roles)
    f.db = MagicMock()
    f.get_all = MagicMock(return_value=[])
    f.get_doc = MagicMock()
    f.parse_json = lambda s: __import__("json").loads(s)
    f.has_permission = MagicMock(return_value=True)
    f.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda fn: fn))
    return f


def _load(frappe_stub):
    perms = types.ModuleType("huf.permissions")
    perms.has_capability = MagicMock(return_value=True)
    mods = {"frappe": frappe_stub, "huf.permissions": perms}
    with patch.dict(sys.modules, mods):
        spec = importlib.util.spec_from_file_location(
            "agent_form_api_under_test", os.path.join(ROOT, "ai", "agent", "agent_form_api.py")
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    m._perms = perms
    return m


class WorkspaceDefaultModel(unittest.TestCase):
    def test_returns_saved_default(self):
        f = _fake_frappe()
        f.db.get_single_value.side_effect = lambda dt, fld: {"default_provider": "OpenAI", "default_model": "gpt-x"}[fld]
        f.db.get_value.return_value = "OpenAI"
        self.assertEqual(_load(f).get_workspace_default_model(), {"provider": "OpenAI", "model": "gpt-x"})

    def test_falls_back_to_first_chat_model(self):
        f = _fake_frappe()
        f.db.get_single_value.return_value = None
        f.get_all.return_value = [
            {"name": "text-embedding-3", "model_name": "text-embedding-3", "provider": "OpenAI", "modalities": "Embeddings"},
            {"name": "gpt-chat", "model_name": "gpt-chat", "provider": "OpenAI", "modalities": "Text"},
        ]
        self.assertEqual(_load(f).get_workspace_default_model(), {"provider": "OpenAI", "model": "gpt-chat"})

    def test_none_safe_when_no_models(self):
        f = _fake_frappe()
        f.db.get_single_value.return_value = None
        self.assertEqual(_load(f).get_workspace_default_model(), {"provider": None, "model": None})

    def test_guest_denied(self):
        f = _fake_frappe(user="Guest")
        with self.assertRaises(_PermErr):
            _load(f).get_workspace_default_model()

    def test_set_requires_system_manager(self):
        f = _fake_frappe(roles=("Huf User",))
        with self.assertRaises(_PermErr):
            _load(f).set_workspace_default_model("OpenAI", "gpt-x")

    def test_set_validates_and_saves(self):
        f = _fake_frappe()
        f.db.get_value.return_value = "OpenAI"
        m = _load(f)
        self.assertEqual(m.set_workspace_default_model(None, "gpt-x"), {"provider": "OpenAI", "model": "gpt-x"})
        f.db.set_single_value.assert_called_once_with(
            "Agent Settings", {"default_provider": "OpenAI", "default_model": "gpt-x"}
        )
        with self.assertRaises(_ValErr):
            m.set_workspace_default_model("Other", "gpt-x")


class DeletePrecheck(unittest.TestCase):
    def _run(self, counts, roles=("System Manager",), can_edit=True):
        f = _fake_frappe(roles=roles)
        doc = MagicMock(owner="o@x.com", disabled=0)
        f.get_doc.return_value = doc
        f.db.count.side_effect = lambda dt, flt=None: counts.get(dt, 0)
        m = _load(f)
        m._perms.has_capability.return_value = can_edit
        with patch.dict(sys.modules, {"huf.permissions": m._perms, "frappe": f}):
            return m.get_agent_delete_precheck("A"), doc

    def test_unlinked_can_delete_no_archive_suggestion(self):
        r, doc = self._run({})
        self.assertTrue(r["can_delete"])
        self.assertFalse(r["suggest_archive"])
        doc.check_permission.assert_called_with("read")

    def test_linked_suggests_archive(self):
        r, _ = self._run({"Agent Conversation": 3, "Agent Run": 5, "Automation": 1})
        self.assertEqual(r["counts"], {"conversations": 3, "runs": 5, "automations": 1, "triggers": 0})
        self.assertTrue(r["suggest_archive"])

    def test_non_admin_cannot_delete(self):
        r, _ = self._run({"Agent Run": 1}, roles=("Huf User",))
        self.assertFalse(r["can_delete"])
        self.assertTrue(r["can_archive"])


class DraftTest(unittest.TestCase):
    def test_requires_write_permission(self):
        f = _fake_frappe()
        doc = MagicMock()
        doc.check_permission.side_effect = _PermErr("no")
        f.get_doc.return_value = doc
        with self.assertRaises(_PermErr):
            _load(f).run_agent_draft_test("A", "hi", {})
        doc.check_permission.assert_called_with("write")

    def test_requires_args(self):
        with self.assertRaises(_ValErr):
            _load(_fake_frappe()).run_agent_draft_test("", "hi")

    def test_overrides_whitelist_and_validation(self):
        f = _fake_frappe()
        f.db.exists.return_value = True
        if True:
            m = _load(f)
            out = m._clean_overrides('{"instructions": "x", "temperature": "0.2", "disabled": 1, "agent_tool": ["t1"]}')
            self.assertEqual(out, {"instructions": "x", "temperature": 0.2, "agent_tool": ["t1"]})
            f.db.exists.return_value = False
            with self.assertRaises(_ValErr):
                m._clean_overrides({"agent_tool": ["nope"]})
            with self.assertRaises(_ValErr):
                m._clean_overrides({"top_p": "abc"})

    def test_apply_draft_overrides_in_memory(self):
        ns = {"apply_draft_overrides": _load(_fake_frappe()).apply_draft_overrides}

        class Row(dict):
            def as_dict(self):
                return dict(self)

            def __getattr__(self, k):
                return self[k]

        class Doc:
            instructions = "old"
            prompt_mode = "Template"
            temperature = 0.7
            top_p = None
            provider = "P"
            model = "M"

            def __init__(self):
                self.rows = [Row(tool="keep", name="r1", idx=1, require_confirmation=1)]
                self.saved = False

            def get(self, k):
                return self.rows

            def set(self, k, v):
                self.rows = list(v)

            def append(self, k, d):
                self.rows.append(Row(d))

            def save(self):
                self.saved = True

        d = Doc()
        ns["apply_draft_overrides"](d, {"instructions": "new", "temperature": 0.2, "agent_tool": ["keep", "added"], "bogus": 1})
        self.assertEqual((d.instructions, d.temperature, d.prompt_mode), ("new", 0.2, "Local"))
        self.assertEqual([r["tool"] for r in d.rows], ["keep", "added"])
        self.assertEqual(d.rows[0].get("require_confirmation"), 1)
        self.assertNotIn("name", d.rows[0])
        self.assertFalse(d.saved)
        self.assertFalse(hasattr(d, "bogus"))


if __name__ == "__main__":
    unittest.main()
