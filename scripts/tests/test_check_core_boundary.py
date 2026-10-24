import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_core_boundary as ccb  # noqa: E402


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class CoreBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.baseline = self.root / "baseline.json"
        self.addCleanup(self._tmp.cleanup)

    def run_guard(self, *extra):
        return ccb.main(["--root", str(self.root), "--baseline", str(self.baseline), *extra])

    def edges(self):
        return ccb.scan(self.root)

    def test_lazy_python_import_is_an_edge(self):
        write(self.root, "huf/ai/gateway_service.py",
              "def f():\n    from huf.ai.whatsapp.outbound_policy import check\n")
        self.assertEqual(self.edges(), ["huf/ai/gateway_service.py -> huf.ai.whatsapp.outbound_policy"])

    def test_from_package_import_and_relative_import(self):
        write(self.root, "huf/ai/a.py", "from huf.ai import solutions\n")
        write(self.root, "huf/ai/b.py", "from .gateway_adapters import whatsapp_bridge\n")
        self.assertEqual(self.edges(), [
            "huf/ai/a.py -> huf.ai.solutions",
            "huf/ai/b.py -> huf.ai.gateway_adapters.whatsapp_bridge",
        ])

    def test_dotted_string_reference_is_an_edge(self):
        write(self.root, "huf/hooks.py", 'x = {"daily": ["huf.ai.whatsapp.send_keys.purge"]}\n')
        self.assertEqual(self.edges(), ["huf/hooks.py -> huf.ai.whatsapp.send_keys.purge"])

    def test_feature_and_test_paths_are_ignored(self):
        body = "from huf.ai.whatsapp import x\n"
        for rel in ("huf/ai/whatsapp/a.py", "huf/ai/solutions/b.py",
                    "huf/ai/gateway_adapters/whatsapp_bridge.py", "huf/ai/tests/test_x.py",
                    "huf/ai/test_y.py"):
            write(self.root, rel, body)
        self.assertEqual(self.edges(), [])

    def test_frontend_alias_relative_and_lazy_imports(self):
        write(self.root, "frontend/src/App.tsx",
              "const P = lazy(() => import('./pages/WhatsAppManagePage'));\n")
        write(self.root, "frontend/src/components/tools/C.tsx",
              "import { x } from '../whatsapp/model';\nimport { y } from '@/services/solutionsApi';\n")
        write(self.root, "frontend/src/components/whatsapp/Own.tsx", "import { z } from '@/services/whatsappApi';\n")
        self.assertEqual(self.edges(), [
            "frontend/src/App.tsx -> pages/WhatsAppManagePage",
            "frontend/src/components/tools/C.tsx -> components/whatsapp/model",
            "frontend/src/components/tools/C.tsx -> services/solutionsApi",
        ])

    def test_new_edge_fails_removed_edge_passes(self):
        write(self.root, "huf/ai/a.py", "import huf.ai.whatsapp\n")
        self.assertEqual(self.run_guard("--update"), 0)
        self.assertEqual(self.run_guard(), 0)
        write(self.root, "huf/ai/b.py", "import huf.ai.solutions\n")
        self.assertEqual(self.run_guard(), 1)
        write(self.root, "huf/ai/b.py", "")
        write(self.root, "huf/ai/a.py", "")
        self.assertEqual(self.run_guard(), 0)

    def test_update_refuses_increase_without_force(self):
        write(self.root, "huf/ai/a.py", "")
        self.assertEqual(self.run_guard("--update"), 0)
        write(self.root, "huf/ai/a.py", "import huf.ai.whatsapp\n")
        self.assertEqual(self.run_guard("--update"), 1)
        self.assertEqual(self.run_guard("--update", "--force"), 0)
        self.assertEqual(self.run_guard(), 0)

    def test_missing_baseline_fails(self):
        self.assertEqual(self.run_guard(), 1)


if __name__ == "__main__":
    unittest.main()
