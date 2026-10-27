import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_standards as rs  # noqa: E402


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "ok.py").write_text("import sys\nsys.exit(0)\n")
        (self.root / "bad.py").write_text("import sys\nprint('boom')\nsys.exit(1)\n")
        (self.root / "upd.py").write_text("import sys\nsys.exit(0 if '--update' in sys.argv else 1)\n")

    def run_with(self, entries, *args):
        m = self.root / "m.json"
        m.write_text(json.dumps(entries))
        return rs.main(["--manifest", str(m), "--root", str(self.root), *args])

    def test_pass_and_fail(self):
        ok = {"name": "ok", "script": "ok.py", "args": [], "paths": ["**"]}
        bad = {"name": "bad", "script": "bad.py", "args": [], "paths": ["**"]}
        self.assertEqual(self.run_with([ok]), 0)
        self.assertEqual(self.run_with([ok, bad]), 1)

    def test_missing_script_is_skipped(self):
        miss = {"name": "later", "script": "check_later.py", "args": [], "paths": ["**"]}
        self.assertEqual(self.run_with([miss]), 0)

    def test_only_and_unknown(self):
        ok = {"name": "ok", "script": "ok.py", "args": [], "paths": ["**"]}
        bad = {"name": "bad", "script": "bad.py", "args": [], "paths": ["**"]}
        self.assertEqual(self.run_with([ok, bad], "--only", "ok"), 0)
        self.assertEqual(self.run_with([ok, bad], "--only", "nope"), 2)

    def test_update_passthrough(self):
        upd = {"name": "upd", "script": "upd.py", "args": [], "paths": ["**"]}
        self.assertEqual(self.run_with([upd]), 1)
        self.assertEqual(self.run_with([upd], "--update"), 0)

    def test_files_filter(self):
        bad = {"name": "bad", "script": "bad.py", "args": [], "paths": ["frontend/src/**"]}
        self.assertEqual(self.run_with([bad], "--files", "huf/x.py"), 0)
        self.assertEqual(self.run_with([bad], "--files", "frontend/src/a/b.ts"), 1)


if __name__ == "__main__":
    unittest.main()
