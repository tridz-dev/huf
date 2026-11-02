# scripts/

## Standards guards

`python3 scripts/run_standards.py` runs every guard listed in
`scripts/standards.json` and prints one table (exit 1 if any guard fails). It runs in CI
(`.github/workflows/standards.yml`, workflow "Standards") and as the `standards`
pre-commit hook. Whole run takes well under a second, so it runs on every commit.

Options: `--only <name>` (repeatable), `--update` (passed to each guard),
`--files a b` (only guards whose manifest `paths` globs match), `-v` (show output of
passing guards). A manifest entry whose script does not exist yet is skipped with a
warning, so guard branches can merge in any order.

Guard tests: `python3 -m unittest discover -s scripts/tests` (also run by the Standards workflow).

### Guards

- `check_file_size.py` (`file-size`): scans `frontend/src` (.ts/.tsx) and `huf/` (.py;
  migrations, patches, tests, fixtures, generated code skipped).
  - a new file over 500 lines fails; a baselined file may not grow
  - a new `services/*Api.ts` over 600 lines fails
  - a directory with more than 15 source files fails if it is new or grew past its baseline
  - files over 300 lines only warn (`-v` lists them)
  - `--list` prints offenders, largest first
- `check_repo_layout.py`: keeps workspace/agent files out of the repo (own workflow).
- Other guards (UI drift, API calls, whitelist) register themselves in `standards.json`.

### Baselines

Existing violations are recorded in `scripts/baselines/<guard>.json` so the guard can be
strict on new code. Baselines only decrease: after splitting a file, run
`python3 scripts/run_standards.py --update` (or the guard's `--update`) and commit the
smaller baseline. `--update` refuses to add or raise an entry; `--force` overrides and
needs owner approval.

### Adding a guard

1. Write `scripts/check_<name>.py`: exit 0 on success, non-zero with readable messages on
   failure, support `--update` if it has a baseline (decrease-only).
2. Add `{ "name", "script", "args", "paths" }` to `scripts/standards.json`. Do not edit CI or
   pre-commit; they call the runner.
3. Add `scripts/tests/test_check_<name>.py` (stdlib `unittest`, no extra dependencies).
