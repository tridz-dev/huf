import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_whitelist as cw  # noqa: E402


def write(root, rel, src):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(src))


class WhitelistTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.baseline = self.root / "baseline.json"
        self.addCleanup(self._tmp.cleanup)

    def run_guard(self, *extra):
        return cw.main(["--root", str(self.root), "--baseline", str(self.baseline), *extra])

    def rules(self, src):
        write(self.root, "huf/m.py", src)
        found, _ = cw.scan(self.root)
        return {f["name"]: f["rules"] for f in found}

    def test_permission_first_is_clean(self):
        out = self.rules("""
            import frappe
            @frappe.whitelist()
            def ok():
                frappe.has_permission("Agent", "read", throw=True)
                return 1
            @frappe.whitelist()
            def helper_ok():
                _can_manage_integrations()
            @frappe.whitelist()
            def bad():
                return frappe.get_all("Agent")
        """)
        self.assertEqual(out, {"bad": ["no_permission"]})

    def test_depth_one_callee_counts(self):
        out = self.rules("""
            import frappe
            def _guard():
                frappe.only_for("System Manager")
            @frappe.whitelist()
            def ep():
                _guard()
        """)
        self.assertEqual(out, {})

    def test_guest_needs_verification(self):
        out = self.rules("""
            import frappe, hmac
            @frappe.whitelist(allow_guest=True)
            def open_hook():
                return 1
            @frappe.whitelist(allow_guest=True, methods=["POST"])
            def signed():
                verify_signature(frappe.request.data)
            def _check(sig):
                return hmac.compare_digest(sig, "x")
            @frappe.whitelist(allow_guest=True)
            def indirect():
                _check("a")
        """)
        self.assertEqual(out, {"open_hook": ["guest_unverified"]})

    def test_mutation_requires_post(self):
        out = self.rules("""
            import frappe
            @frappe.whitelist()
            def get_style():
                frappe.has_permission("X")
                frappe.db.set_value("X", "a", "b", 1)
            @frappe.whitelist(methods=["POST"])
            def post_style():
                frappe.has_permission("X")
                frappe.db.set_value("X", "a", "b", 1)
            @frappe.whitelist()
            def list_insert():
                frappe.has_permission("X")
                items = []
                items.insert(0, "x")
        """)
        self.assertEqual(out, {"get_style": ["mutating_get"]})

    def test_baseline_cannot_grow(self):
        write(self.root, "huf/a.py", "import frappe\n@frappe.whitelist()\ndef f():\n    return 1\n")
        self.assertEqual(self.run_guard("--update"), 0)
        self.assertEqual(self.run_guard(), 0)
        write(self.root, "huf/b.py", "import frappe\n@frappe.whitelist()\ndef g():\n    return 1\n")
        self.assertEqual(self.run_guard(), 1)
        self.assertEqual(self.run_guard("--update"), 1)
        self.assertEqual(self.run_guard("--update", "--force"), 0)
        self.assertEqual(self.run_guard(), 0)
        data = json.loads(self.baseline.read_text())
        self.assertEqual(data["totals"]["no_permission"], 2)

    def test_baseline_can_shrink(self):
        write(self.root, "huf/a.py", "import frappe\n@frappe.whitelist()\ndef f():\n    return 1\n")
        self.run_guard("--update")
        write(self.root, "huf/a.py", "import frappe\n@frappe.whitelist()\ndef f():\n    frappe.only_for('X')\n")
        self.assertEqual(self.run_guard(), 0)
        self.assertEqual(self.run_guard("--update"), 0)
        self.assertEqual(json.loads(self.baseline.read_text())["totals"]["no_permission"], 0)

    def test_tests_dir_ignored(self):
        write(self.root, "huf/tests/t.py", "import frappe\n@frappe.whitelist()\ndef f():\n    return 1\n")
        self.assertEqual(cw.scan(self.root)[0], [])


if __name__ == "__main__":
    unittest.main()
