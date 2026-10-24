import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_file_size as cfs  # noqa: E402


def write(root, rel, lines):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n" * lines)


class FileSizeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.baseline = self.root / "baseline.json"
        self.addCleanup(self._tmp.cleanup)

    def run_guard(self, *extra):
        return cfs.main(["--root", str(self.root), "--baseline", str(self.baseline), *extra])

    def test_new_big_file_fails(self):
        write(self.root, "frontend/src/a.ts", 10)
        self.assertEqual(self.run_guard("--update"), 0)
        write(self.root, "frontend/src/big.tsx", 501)
        self.assertEqual(self.run_guard(), 1)

    def test_baseline_file_may_not_grow(self):
        write(self.root, "huf/big.py", 600)
        self.run_guard("--update")
        self.assertEqual(self.run_guard(), 0)
        write(self.root, "huf/big.py", 601)
        self.assertEqual(self.run_guard(), 1)
        write(self.root, "huf/big.py", 550)
        self.assertEqual(self.run_guard(), 0)

    def test_new_service_api_over_600(self):
        write(self.root, "frontend/src/services/a.ts", 1)
        self.run_guard("--update")
        write(self.root, "frontend/src/services/fooApi.ts", 450)
        self.assertEqual(self.run_guard(), 0)
        write(self.root, "frontend/src/services/fooApi.ts", 601)
        self.assertEqual(self.run_guard(), 1)

    def test_folder_rule(self):
        for i in range(16):
            write(self.root, f"frontend/src/pages/p{i}.ts", 1)
        self.run_guard("--update")
        self.assertEqual(self.run_guard(), 0)
        write(self.root, "frontend/src/pages/extra.ts", 1)
        self.assertEqual(self.run_guard(), 1)
        for i in range(16):
            write(self.root, f"frontend/src/newdir/p{i}.ts", 1)
        (self.root / "frontend/src/pages/extra.ts").unlink()
        self.assertEqual(self.run_guard(), 1)  # new folder over limit

    def test_update_refuses_increase_unless_forced(self):
        write(self.root, "huf/big.py", 600)
        self.run_guard("--update")
        write(self.root, "huf/big.py", 700)
        self.assertEqual(self.run_guard("--update"), 1)
        self.assertEqual(json.loads(self.baseline.read_text())["files"]["huf/big.py"], 600)
        self.assertEqual(self.run_guard("--update", "--force"), 0)
        write(self.root, "huf/big.py", 520)
        self.assertEqual(self.run_guard("--update"), 0)
        self.assertEqual(json.loads(self.baseline.read_text())["files"]["huf/big.py"], 520)

    def test_excluded_paths_and_warning_do_not_fail(self):
        write(self.root, "huf/migrations/m.py", 900)
        write(self.root, "huf/tests/t.py", 900)
        write(self.root, "huf/mid.py", 400)
        self.run_guard("--update")
        self.assertEqual(self.run_guard(), 0)
        files, _ = cfs.scan(self.root)
        self.assertEqual(set(files), {"huf/mid.py"})

    def test_missing_baseline_fails_and_list_ok(self):
        write(self.root, "huf/a.py", 1)
        self.assertEqual(self.run_guard(), 1)
        self.assertEqual(self.run_guard("--list"), 0)


if __name__ == "__main__":
    unittest.main()
