# Huf Skills System — Phase 2 Execution Plan

> Branch: `feature/skills-system`
> Builds on: `doc/skills-phase1-gap-analysis.md`, `SKILLS_FUTURE.md` (Phase 2)
> Date: 2026-06-13
> Scope: **Phase 2 — Restricted execution + package management.** Add `run_python` / `run_node` so skills.sh document/data skills work. Packages installed at skill-install time from a trusted list. NO runtime `pip install`, NO containers (that is Phase 3).

---

## 1. What Phase 2 delivers

1. Two runtime tools — `run_python` and `run_node` — that a skill can expose. The agent reads the skill's `SKILL.md`, generates code, calls the tool, and gets stdout / produced files back. This makes most skills.sh skills work unchanged.
2. A **managed package layer**: a dedicated Python virtualenv (and Node `node_modules`) provisioned from an admin-chosen **install profile** (`none` / `basic` / `standard` / `full`). Packages come only from a trusted list; never from agent-supplied input at runtime.
3. Package setup surfaced in three UI places: setup wizard step, Agent Settings, and a Skills-page banner.
4. Hard gating: execution is off unless `skill_execution_enabled: 1` is set in `site_config.json`.

Explicitly **out of scope** (Phase 3): containers, runtime `pip install`, remote/managed execution backends, per-run network egress. The execution call site is abstracted so Phase 3 can swap the backend without touching skills or tools.

---

## 2. Key architectural decisions (resolve before coding)

| # | Decision | Recommendation | Why |
|---|----------|----------------|-----|
| D1 | **Execution engine** | **Controlled subprocess in a managed venv** as the workhorse; RestrictedPython only as an optional fast-path for trivial pure-Python snippets. | RestrictedPython cannot import C-extension libs (`pandas`, `pypdf`, `pillow`, `lxml`). The target skills.sh skills *require* real imports. A locked-down subprocess (no network, temp CWD, rlimits, timeout, non-root) is the only thing that runs them. The plan's "RestrictedPython + controlled subprocess" phrasing resolves to "subprocess is primary." |
| D2 | **Where the venv lives** | `sites/<site>/private/skills/venv/` (per-site, private, git-ignored). Node deps in `sites/<site>/private/skills/node/`. | Per-site isolation; private dir is not web-served; survives migrations; mirrors Frappe's `private/files` convention. |
| D3 | **When packages install** | At **skill install time** and at **explicit profile-apply time** — never at agent runtime. | Matches the plan; keeps the request path fast and removes arbitrary-install attack surface. |
| D4 | **Trusted list source of truth** | Ship a default profile→packages map in code (`packages.py`); allow admin override stored in `Agent Settings.skill_trusted_packages` (JSON). A skill's `SKILL.md` `compatibility.requires` list is honored only if every entry is on the resolved trusted list. | Admin stays in control; a malicious manifest cannot pull arbitrary packages. |
| D5 | **Network during execution** | Denied by default for `run_python`/`run_node`. HTTP stays the existing SSRF-guarded `GET`/`POST` tools. | Smallest blast radius; Phase 3 reintroduces guarded egress inside containers. |
| D6 | **How run tools attach to a skill** | A skill flags `execution_required` (or declares `run_python`/`run_node` in its `SKILL.md` `huf:` block); `loader.py` auto-creates the run tool for that agent, exactly like `create_list_skills_tool`. | Reuses the proven Phase 1 runtime-tool pattern; no per-skill `Agent Tool Function` rows needed for the generic runners. |

---

## 3. Prerequisites carried from Phase 1

These Phase 1 gaps must close first (small, listed in the gap analysis); Phase 2 depends on them:

- **`SKILL.md` `requirements` field** — `_parse_skill_manifest` (`importer.py`) must read `compatibility.requires` (standard field) and `huf.node_requirements` from the `SKILL.md` frontmatter and store them on the `Skill` doc (new `requirements` / `node_requirements` Long Text fields). Without this, Phase 2 cannot know what a skill needs.
- **Agent Settings JSON fields** — `skill_destinations`, `last_skill_scans` (Phase 1) plus the Phase 2 fields in §5. The code already `hasattr`-guards these.
- **`.huf` packaging** (Phase 1) is *not* a hard blocker for execution, but the `SKILL.md` `compatibility.requires` / `huf:` block must include `requirements` keys so Phase 2 data flows through export/import. `manifest.json` is not used — `SKILL.md` is the canonical format.

---

## 4. Backend — files to add / modify

### 4.1 New package: `huf/ai/skills/execution/`

| File | Responsibility |
|------|----------------|
| `__init__.py` | Package marker; exports the public `run_python` / `run_node` entry points. |
| `packages.py` | Profile definitions (`none`/`basic`/`standard`/`full`) and the default trusted package list (the exact lists from `SKILLS_FUTURE.md` §Phase 2). `resolve_profile()` merges defaults with `Agent Settings.skill_trusted_packages`. Pure data + validation; no side effects. |
| `venv_manager.py` | `ensure_venv()` (create `private/skills/venv` if missing, idempotent), `install_profile(profile)` (install/uninstall to match the profile, run in background job), `installed_packages()`, `node_install(profile)`. All `pip`/`npm` calls are `subprocess.run` with timeout + allowlist of package names (no arbitrary args). Mirrors `importer.py:_run_git_clone` hardening (timeout, no shell, captured output). |
| `python_runner.py` | `run_python_code(code, files=None, timeout=...)`: write code + input files to a fresh temp dir, exec the venv's interpreter as a subprocess with: CWD=temp dir, scrubbed env (no secrets, `PATH` to venv only), no network (best-effort: `unshare`/`HUF_NO_NET` guard where available; documented limitation otherwise), `resource` rlimits (CPU, address space, file size, no fork where possible), wall-clock timeout, non-root. Returns `{stdout, stderr, exit_code, files: [{name, file_url}]}` — produced files saved via Frappe `save_file` into `private/files`. |
| `node_executor.py` | `run_node_code(code, files=None, timeout=...)`: same contract for Node, using the managed `node_modules`. The `node_executor.py` named in the future plan. |
| `runtime_tools.py` | `create_run_python_tool(agent_name)` / `create_run_node_tool(agent_name)` — `FunctionTool` factories with the JSON schema (`{code: string, ...}`), built the same way as `create_list_skills_tool` in `loader.py`. Returns `None` when execution is disabled or no attached skill needs it. |
| `gating.py` (or fold into `packages.py`) | `execution_enabled()` reads `site_config.skill_execution_enabled`; `execution_mode()` reads `skill_execution_mode` (default `restricted`; Phase 3 adds `local_docker`/`e2b`). Single chokepoint so Phase 3 only edits here. |

### 4.2 Modify existing files

| File | Change |
|------|--------|
| `huf/ai/skills/loader.py` | New `create_skill_execution_tools(agent_name)` that, when `gating.execution_enabled()` and any attached skill has `execution_required`, returns `[run_python, run_node]` from `runtime_tools.py`. Call it where `create_list_skills_tool` is wired into `AgentManager._setup_tools`. Add `get_skill_prompts` if Phase 1 prompt-wiring still open (gap §4.2). |
| `huf/ai/skills/importer.py` | In `_parse_skill_manifest`: read `compatibility.requires` and `huf.node_requirements` from `SKILL.md` frontmatter. In `_create_or_update_skill`: persist them and set `execution_required` when present. After a successful import, if execution is enabled, call `venv_manager.install_requirements(skill.requirements)` **validated against the trusted list** (reject + warn on anything off-list; surface in `Skill Import Log`). |
| `huf/ai/skills/api.py` | New whitelisted endpoints: `get_execution_status()`, `apply_install_profile(profile)` (enqueues `venv_manager.install_profile`), `get_install_profiles()`, `get_trusted_packages()`. All admin-gated (`frappe.only_for("System Manager")`). |
| `huf/ai/skills/hooks.py` | On `after_migrate`/`after_app_install`, if a profile is configured and the venv is missing, enqueue a provision job (skippable, background). |
| `huf/hooks.py` | No new event types needed — reuse existing `after_migrate`. Add the background job to `scheduler_events`/`enqueue` only if eager provisioning is wanted. |
| `huf/install.py` | Seed `Agent Settings` defaults: `skill_install_profile = "standard"` is **not** auto-applied (no surprise installs); seed the trusted-package list default. |
| `.gitignore` | Ignore `sites/*/private/skills/`. |

### 4.3 `Agent Tool Function` (optional, secondary)

The generic `run_python`/`run_node` cover the skills.sh model and need **no** `Agent Tool Function` change. The future plan's "extend with `Script`/`Node` source types" is only for skills that ship a *named, pre-written* script as a first-class tool. Recommend **deferring** that to a 2b sub-milestone — add `Script` and `Node` to the `types` Select and a `script_code` Code field, with `loader._resolve_tool_function_path` routing them through `python_runner`/`node_executor`. Not required for skills.sh compatibility.

---

## 5. DocType changes

**`Agent Settings`** — add fields (all optional, `hasattr`-safe):

| Field | Type | Purpose |
|-------|------|---------|
| `skill_destinations` | JSON / Long Text | (Phase 1 gap) custom common destinations. |
| `last_skill_scans` | JSON / Long Text | (Phase 1 gap) app-scan cache. |
| `skill_install_profile` | Select (`none`/`basic`/`standard`/`full`) | active profile; default blank (unset → banner shows). |
| `skill_trusted_packages` | JSON / Long Text | admin override/extension of the trusted list. |
| `skill_execution_status` | Small Text (read-only) | last provision result / installed-profile summary, written by `venv_manager`. |

**`Skill`** — add fields:

| Field | Type | Purpose |
|-------|------|---------|
| `requirements` | JSON / Long Text | Python packages the skill needs (from `SKILL.md` `compatibility.requires`). |
| `node_requirements` | JSON / Long Text | Node packages. |
| `execution_required` | Check | set true when the skill declares a runner; drives `loader` tool attach. |

No new DocTypes are required for Phase 2.

---

## 6. Frontend — files to add / modify

| File | Change |
|------|--------|
| `frontend/src/services/skillApi.ts` | Add `getExecutionStatus`, `applyInstallProfile`, `getInstallProfiles`, `getTrustedPackages` (via `call`/`db`, per the service-layer convention). |
| Setup wizard (locate existing onboarding flow; if none, a first-run step) | New **"Skill execution"** step: profile selector (`none`/`basic`/`standard`/`full`, default `standard`), "Install" runs `applyInstallProfile` in background, skippable. |
| Agent Settings page | New section: profile selector + Install button + progress/status from `skill_execution_status`; shows installed packages. Accessible any time. |
| `frontend/src/pages/SkillsPage.tsx` | Banner when no profile is set (`skill_install_profile` empty) linking to the Agent Settings section — the "Skills page banner" from the plan. |
| `frontend/src/components/skills/SkillImportModal.tsx` | Show the skill's `requirements` and whether each is covered by the active profile (dependency warnings — also a Phase 1 gap). |
| `frontend/src/pages/SkillFormPage.tsx` (optional) | Surface `run_python`/`run_node` as available when `execution_required`; read-only indicator. |
| Routes/sidebar | No new routes needed; reuse Agent Settings + Skills pages. |

---

## 7. Security model (must hold)

1. **Gated off by default** — nothing executes unless `skill_execution_enabled: 1` in `site_config.json`. The tools are not even attached otherwise.
2. **No runtime package installs** — `run_python`/`run_node` never invoke `pip`/`npm`. Only `venv_manager` does, only from the trusted list, only via admin action / install.
3. **Trusted-list enforcement** — `SKILL.md` `compatibility.requires` entries are intersected with the resolved trusted list; off-list packages are refused and logged, never installed.
4. **Subprocess hardening** — non-root, scrubbed env (no Frappe secrets/site config in the child env), temp CWD deleted after run, `resource` rlimits (CPU time, memory, file size, process count), wall-clock timeout, captured stdout/stderr with size caps, `shell=False`, fixed interpreter path (the managed venv only).
5. **No network egress** from runners (D5); HTTP stays on the SSRF-guarded tools.
6. **Admin-only control endpoints** — `apply_install_profile` etc. require `System Manager`.
7. **Output handling** — produced files saved as **private** Frappe files; stdout returned to the agent is size-capped; never echo env or secrets.
8. **Reuse, don't reinvent** — model the subprocess calls on `importer.py:_run_git_clone` (timeout, no shell, error capture) and keep the SSRF guard untouched.

---

## 8. Testing

- **Unit (`huf/ai/skills/tests/`)**: `packages.resolve_profile` (profile math, admin override merge, off-list rejection); `venv_manager` install/uninstall against a temp venv (or mocked subprocess); `python_runner` happy path (returns stdout), timeout path (killed), file-output path, env-scrub assertion (a secret in site config is NOT visible to the child), gating off → tool not created.
- **Integration**: import a fixture skill declaring `requirements: ["pypdf"]` under the `standard` profile → tool attaches → agent calls `run_python` to read a PDF → file returned. A skill requiring an off-list package → import warns, tool still attaches but the package is absent (documented failure).
- **Negative/security**: off-list package refused; runtime `pip install ...` inside `run_python` code cannot reach the network / has no effect; oversized stdout truncated; non-zero exit surfaced cleanly.
- **Regression**: with `skill_execution_enabled` unset, behavior is identical to Phase 1 (no run tools, no venv).

---

## 9. Suggested sequencing

1. **2.0 — Prereqs** (close Phase 1 gaps the rest depends on): `SKILL.md` `compatibility.requires` / `huf:` parsing in importer, `Skill` execution fields, `Agent Settings` JSON fields. Small, unblocks everything.
2. **2.1 — Execution core** (no UI): `packages.py`, `gating.py`, `venv_manager.py`, `python_runner.py`, unit tests. Provision a venv by hand, run code from a test. Highest-risk, do it first.
3. **2.2 — Tool wiring**: `runtime_tools.py` + `loader.py` attach + `AgentManager` hookup. End-to-end: enabled skill → agent calls `run_python`.
4. **2.3 — Install management**: `api.py` endpoints + importer install-time hook + trusted-list enforcement + `Skill Import Log` surfacing.
5. **2.4 — Node**: `node_executor.py` + `run_node` (mirror 2.1–2.3). Can ship after Python.
6. **2.5 — Frontend**: Agent Settings section → Skills banner → setup wizard step → import-modal dependency warnings.
7. **2.6 — Starter skills**: add 1–2 execution skills (PDF, docx) to the `huf-skills` repo to validate the whole path.

Ship gate for "Phase 2 done": with `skill_execution_enabled: 1` and the `standard` profile, importing the docx/pdf starter skills lets an agent generate code, call `run_python`, and get a file back — with execution disabled, the system behaves exactly as Phase 1.

---

## 10. Open decisions to confirm

| Question | Default if unanswered |
|----------|----------------------|
| RestrictedPython fast-path worth the complexity, or subprocess-only? | **Subprocess-only** for Phase 2 (simpler, one path). |
| Eager venv provisioning on `after_migrate`, or strictly user-triggered? | **User-triggered** (no surprise multi-minute installs on migrate). |
| Per-agent vs per-site profile? | **Per-site** (matches Phase 1 site-level scope). |
| Node.js in Phase 2 or defer to 2.x? | **Defer to 2.4**, ship Python first. |
| Background job runner for installs (Frappe `enqueue`) vs sync with progress? | **`enqueue`** with status polled via `skill_execution_status`. |

---

## 11. File change summary

**Add:** `huf/ai/skills/execution/{__init__,packages,gating,venv_manager,python_runner,node_executor,runtime_tools}.py`; `huf/ai/skills/tests/` execution tests; starter execution skills in `huf-skills`.
**Modify:** `huf/ai/skills/{loader,importer,api,hooks}.py`; `huf/install.py`; `huf/hooks.py` (only if eager provisioning); `.gitignore`; `Agent Settings` + `Skill` doctype JSON; `frontend/src/services/skillApi.ts`; `frontend/src/pages/SkillsPage.tsx`; `frontend/src/components/skills/SkillImportModal.tsx`; Agent Settings page; setup wizard.
**Config:** `site_config.json` keys `skill_execution_enabled` (gate), `skill_execution_mode` (`restricted`, Phase 3-ready).
