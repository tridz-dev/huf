"""Tests for scripts/check_api_calls.py (run: python3 -m pytest scripts/tests)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_api_calls as m  # noqa: E402


def test_count_urls_outside_services():
    src = "const a = '/api/method/huf.x';\nconst b = `${base}/api/resource/Foo`;\n// '/api/method/commented'\n"
    assert m.count_file("components/A.tsx", src) == {"urls": 2, "fetch": 0, "helpers": 0}


def test_services_and_api_ts_exempt_from_urls_and_fetch():
    src = "fetch('/api/method/x'); const u = '/api/method/y';"
    assert m.count_file("services/fooApi.ts", src) == {"urls": 0, "fetch": 0, "helpers": 0}
    assert m.count_file("lib/api.ts", src) == {"urls": 0, "fetch": 0, "helpers": 0}


def test_fetch_detection():
    src = "await fetch(url);\nwindow.fetch (u);\nqueryClient.fetch(x);\nprefetch(x);\n"
    assert m.count_file("components/A.tsx", src)["fetch"] == 2


@pytest.mark.parametrize("line", [
    "async function invoke<T>(a: string) {}",
    "export function unwrapResult<T>(r: unknown) {}",
    "const unwrap = (r) => r;",
    "export const callApi = async () => {};",
])
def test_helper_definitions_flagged_everywhere_but_api_ts(line):
    assert m.count_file("services/xApi.ts", line)["helpers"] == 1
    assert m.count_file("lib/api.ts", line)["helpers"] == 0


def test_helper_calls_not_flagged():
    assert m.count_file("services/xApi.ts", "const r = await invoke('a');\nreturn unwrapResult(r);")["helpers"] == 0


def test_compare_detects_increase_and_new_file():
    base = {"a.ts": {"urls": 1}}
    assert m.compare({"a.ts": {"urls": 1}}, base) == []
    assert m.compare({"a.ts": {"urls": 0}}, base) == []
    assert len(m.compare({"a.ts": {"urls": 2}}, base)) == 1
    assert len(m.compare({"a.ts": {"urls": 1, "fetch": 1}}, base)) == 1
    assert "new file" in m.compare({"b.ts": {"fetch": 1}}, base)[0]


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    src = tmp_path / "frontend" / "src" / "components"
    src.mkdir(parents=True)
    (src / "A.tsx").write_text("const u = '/api/method/x';\n")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "BASELINE", tmp_path / "scripts" / "baselines" / "api_calls.json")
    return tmp_path


def _run(fake_repo, *args):
    return m.main(list(args))


def test_cli_flow(fake_repo, capsys):
    assert _run(fake_repo, "--update") == 1  # raising from empty baseline is refused
    assert _run(fake_repo, "--update", "--force") == 0
    assert json.loads(m.BASELINE.read_text()) == {"components/A.tsx": {"urls": 1}}
    assert _run(fake_repo) == 0

    (fake_repo / "frontend/src/components/B.tsx").write_text("fetch('/x');\n")
    assert _run(fake_repo) == 1
    assert "B.tsx" in capsys.readouterr().out
    assert _run(fake_repo, "--update") == 1

    (fake_repo / "frontend/src/components/B.tsx").unlink()
    (fake_repo / "frontend/src/components/A.tsx").write_text("const x = 1;\n")
    assert _run(fake_repo) == 0
    assert _run(fake_repo, "--update") == 0
    assert json.loads(m.BASELINE.read_text()) == {}


def test_list(fake_repo, capsys):
    assert _run(fake_repo, "--list") == 0
    assert "components/A.tsx: urls=1" in capsys.readouterr().out
