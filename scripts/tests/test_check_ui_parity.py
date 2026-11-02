import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_ui_parity as cp  # noqa: E402


def w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class ParityTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)
        self.addCleanup(self._t.cleanup)
        self.ex = self.root / "ex.json"
        self.ex.write_text("{}")
        orig = cp.SCOPED_DOCTYPES
        cp.SCOPED_DOCTYPES = ["gateway"]
        self.addCleanup(lambda: setattr(cp, "SCOPED_DOCTYPES", orig))
        fields = [
            {"fieldname": "a_field", "fieldtype": "Data"},
            {"fieldname": "sec", "fieldtype": "Section Break"},
            {"fieldname": "ro", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "hid", "fieldtype": "Data", "hidden": 1},
        ]
        w(self.root, "huf/huf/doctype/gateway/gateway.json", json.dumps({"fields": fields}))
        w(self.root, "huf/ai/gateways/api.py",
          "import frappe\n@frappe.whitelist()\ndef do_it():\n    pass\n@frappe.whitelist()\ndef other():\n    pass\n")

    def run_main(self, *extra):
        return cp.main(["--root", str(self.root), "--exemptions", str(self.ex), *extra])

    def test_only_editable_fields_required(self):
        self.assertEqual(set(cp.required_fields(self.root, ["gateway"])), {"gateway.a_field"})

    def test_uncovered_fails_then_covered_passes(self):
        self.assertEqual(self.run_main(), 1)
        w(self.root, "frontend/src/components/F.tsx", "a_field")
        w(self.root, "frontend/src/services/s.ts", "huf.ai.gateways.api.do_it other")
        w(self.root, "frontend/src/components/G.tsx", "import {x} from '../services/s'")
        self.assertEqual(self.run_main(), 0)

    def test_service_only_field_not_covered(self):
        w(self.root, "frontend/src/services/s.ts", "a_field")
        _, unc, _ = cp.evaluate(self.root, {})
        self.assertIn("gateway.a_field", unc)

    def test_unimported_service_not_covered(self):
        w(self.root, "frontend/src/services/s.ts", "do_it other")
        _, unc, _ = cp.evaluate(self.root, {})
        self.assertIn("huf.ai.gateways.api.do_it", unc)

    def test_exemption_rules(self):
        ex = {"gateway.a_field": {"reason": "", "kind": "bogus", "owner": "x"}}
        _, unc, errs = cp.evaluate(self.root, ex)
        self.assertNotIn("gateway.a_field", unc)
        self.assertTrue(any("missing reason" in e for e in errs))
        self.assertTrue(any("kind" in e for e in errs))

    def test_stale_and_expired(self):
        w(self.root, "frontend/src/components/F.tsx", "a_field")
        ex = {
            "gateway.a_field": {"reason": "r", "kind": "system", "owner": "x"},
            "huf.ai.gateways.api.do_it": {"reason": "r", "kind": "planned", "owner": "x", "expires": "2000-01-01"},
        }
        _, _, errs = cp.evaluate(self.root, ex)
        self.assertTrue(any("stale" in e for e in errs))
        self.assertTrue(any("expired" in e for e in errs))

    def test_emit(self):
        out = self.root / "o.json"
        self.run_main("--emit", str(out))
        self.assertEqual(json.loads(out.read_text()), {"gateway": ["a_field"]})


if __name__ == "__main__":
    unittest.main()
