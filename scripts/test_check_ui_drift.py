"""Tests for scripts/check_ui_drift.py. Run: python3 -m unittest scripts.test_check_ui_drift"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ui_drift as d  # noqa: E402


class ScanTextTests(unittest.TestCase):
    def test_raw_elements_counted_outside_ui_only(self):
        src = "<label>a</label><input /><select></select><textarea/><Input /><Label/>"
        self.assertEqual(d.scan_text(src, "pages/X.tsx"), {"raw_element": 4})
        self.assertEqual(d.scan_text(src, "components/ui/input.tsx"), {})

    def test_fixed_height_only_on_control_tags(self):
        src = '<Input className="h-8 w-full" /><div className="h-8" /><Button\n  size="sm"\n  className={cn("x", "h-10")}\n/>'
        self.assertEqual(d.scan_text(src, "a.tsx"), {"fixed_height": 2})

    def test_fixed_height_ignores_min_max_and_other_sizes(self):
        src = '<Input className="min-h-8 max-h-9 h-12 h-6.5 h-control-md sm:h-7" />'
        self.assertEqual(d.scan_text(src, "a.tsx"), {"fixed_height": 1})

    def test_fixed_height_in_ui_still_counted(self):
        self.assertEqual(d.scan_text('<Button className="h-9" />', "components/ui/x.tsx"), {"fixed_height": 1})

    def test_text_px_and_style(self):
        src = '<p className="text-[11px] text-[0.8rem]" style={{ width: 4 }} /><i style={{a:1}} />'
        self.assertEqual(d.scan_text(src, "a.tsx"), {"text_px": 1, "inline_style": 2})

    def test_hex_only_in_strings_of_tsx(self):
        src = 'const a = "#fff"; const b = `bg-[#12ab34]`; <a href="#section-one"/> // #abcdef\n/* "#000" */'
        self.assertEqual(d.scan_text(src, "a.tsx"), {"hex_colour": 2})
        self.assertEqual(d.scan_text(src, "a.ts"), {})

    def test_comments_ignored(self):
        src = "// <label> text-[10px]\n/* <input style={{}} */\n<div/>"
        self.assertEqual(d.scan_text(src, "a.tsx"), {})

    def test_is_scanned(self):
        self.assertTrue(d.is_scanned("pages/A.tsx"))
        self.assertFalse(d.is_scanned("pages/A.test.tsx"))
        self.assertFalse(d.is_scanned("pages/__tests__/A.tsx"))
        self.assertFalse(d.is_scanned("types.d.ts"))
        self.assertFalse(d.is_scanned("index.css"))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src = root / "src"
        (self.src / "pages").mkdir(parents=True)
        self.base = root / "base.json"
        self.page = self.src / "pages" / "A.tsx"
        self.page.write_text('<label>x</label><p className="text-[10px]"/>')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = d.main(["--src", str(self.src), "--baseline", str(self.base), *args])
        return rc, out.getvalue(), err.getvalue()

    def test_missing_baseline_fails_then_update_creates(self):
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.run_cli("--update")[0], 0)
        self.assertEqual(self.run_cli()[0], 0)
        data = json.loads(self.base.read_text())
        self.assertEqual(data["files"]["pages/A.tsx"], {"raw_element": 1, "text_px": 1})

    def test_increase_fails_with_grouped_report(self):
        self.run_cli("--update")
        self.page.write_text('<label/><label/><p className="text-[10px]"/>')
        rc, _, err = self.run_cli()
        self.assertEqual(rc, 1)
        self.assertIn("pages/A.tsx", err)
        self.assertIn("raw_element: 1 -> 2", err)
        self.assertNotIn("text_px: 1 -> ", err)

    def test_new_file_with_counts_fails_clean_new_file_passes(self):
        self.run_cli("--update")
        (self.src / "pages" / "B.tsx").write_text("<div/>")
        self.assertEqual(self.run_cli()[0], 0)
        (self.src / "pages" / "B.tsx").write_text('<div style={{a: 1}} />')
        rc, _, err = self.run_cli()
        self.assertEqual(rc, 1)
        self.assertIn("pages/B.tsx", err)

    def test_decrease_passes_and_update_ratchets(self):
        self.run_cli("--update")
        self.page.write_text("<div/>")
        rc, out, _ = self.run_cli()
        self.assertEqual(rc, 0)
        self.assertIn("--update", out)
        self.assertEqual(self.run_cli("--update")[0], 0)
        self.assertEqual(json.loads(self.base.read_text())["files"], {})

    def test_update_refuses_increase_unless_force(self):
        self.run_cli("--update")
        before = self.base.read_text()
        self.page.write_text('<label/><label/><p className="text-[10px]"/>')
        rc, _, err = self.run_cli("--update")
        self.assertEqual(rc, 1)
        self.assertIn("Refusing", err)
        self.assertEqual(self.base.read_text(), before)
        self.assertEqual(self.run_cli("--update", "--force")[0], 0)
        self.assertEqual(self.run_cli()[0], 0)

    def test_list(self):
        rc, out, _ = self.run_cli("--list")
        self.assertEqual(rc, 0)
        self.assertIn("pages/A.tsx\traw_element=1 text_px=1", out)
        self.assertIn("TOTAL", out)


if __name__ == "__main__":
    unittest.main()
