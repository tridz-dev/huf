# Skills System — Future Plan

> Current phase is complete. This documents the skills feature for consideration in a future phase.

---

## What This Is

A packaging and distribution format for Huf agent capabilities. Skills bundle tools + knowledge + prompts into one portable unit that can be shared, imported, and installed — similar to how VS Code extensions or Frappe apps work.

The key insight: skills are only worth building if they give access to a community ecosystem. Grouping existing Huf resources alone is not enough justification.

---

## Core Idea

A skill is a `.huf` file (zip) with `SKILL.md` as the canonical format. `SKILL.md` is the single source of truth — metadata, instructions, and Huf-specific wiring all live there. No separate `manifest.json` needed.

```
my-skill.huf
├── SKILL.md            ← canonical: frontmatter metadata + instructions
├── tools/
│   ├── __init__.py
│   ├── pdf_tools.py    ← Python tool implementations (Phase 2+)
│   └── node_tools/
│       └── transform.js
├── fixtures/
│   ├── knowledge/      ← Knowledge Source fixtures
│   └── prompts/        ← Agent Prompt fixtures
└── hooks.py            ← huf_tools registration
```

### SKILL.md format

Standard Anthropic/Claude frontmatter fields (`name`, `description`, `allowed-tools`, `compatibility`) plus a `huf:` extension block for Huf-specific wiring. Claude/Kimi ignore the `huf:` block; Huf reads everything.

```markdown
---
name: sales-crm
description: CRM and sales operations. Use when user asks about leads, orders, or customers.
compatibility:
  requires: [pypdf]       # Phase 2+ package hint

huf:
  version: "1.0.0"
  author: "tridz-dev"
  category: "CRM"
  tools:
    - get_sales_orders
    - create_lead
  knowledge:
    - source: "Sales Playbook"
      mode: mandatory
  prompts:
    - "Sales Response Template"
  mcp_servers:
    - frappe-crm-mcp
---

# Sales CRM Skill

When the user asks about sales pipelines, leads, or orders...
```

Skills from skills.sh with no `huf:` block import fine — instructions load, tools are wired manually afterward.

An agent attaches skills. At runtime, skill tools/knowledge/prompts are merged into the agent alongside its own.

---

## Why It Is Valuable

- **Not just grouping** — tools/knowledge/prompts are already reusable individually. Skills add value only through packaging + distribution.
- **Community ecosystem** — import any skill from GitHub or a marketplace with one click. Thousands of pre-built capabilities.
- **Export/share** — package your agent's capabilities as a `.huf` file and share with anyone.
- **SKILL.md compatibility** — the instruction layer is compatible with Anthropic/Kimi skill format. Different execution layer, same instructions.

---

## Execution Model

Skills that require runtime code execution (e.g. docx, pdf, data processing) use a `run_python` / `run_node` tool that the agent calls with generated code. The execution backend is an **infrastructure concern, not a skill concern** — the same skill works unchanged as the backend is upgraded across phases.

### Install Model (how skill code enters the system)

**Tier 1 — Dynamic load (UI import, no bench)**
- Skill extracted to `huf/installed_skills/{skill_name}/`
- Huf dynamically loads the Python module
- Tools register via existing `huf_tools` hook pattern
- Admin-gated via `skill_install_enabled` in site_config

**Tier 2 — Proper Frappe app (bench, production)**
- The same `.huf` zip is a valid minimal Frappe app
- `bench get-app` + `bench install-app` for production installs
- `huf_tools` hook fires on `after_migrate` automatically
- Full trust, no dynamic loading

### Code Execution Progression

**Phase 1 — No execution (packaging only)**
- No `run_python` tool exists yet
- Skills bundle pre-built tools/knowledge/prompts only
- skills.sh skills that require code execution won't work yet
- Establishes the format and UX

**Phase 2 — Restricted execution with managed packages**
- `run_python` and `run_node` tools added (RestrictedPython + controlled subprocess)
- No `pip install` at runtime — packages installed at skill install time from a trusted list
- Trusted package list managed in Agent Settings (admin-controlled, default list ships with Huf)
- Package installation exposed in three places:
  - Setup wizard step on fresh install (skippable, runs in background)
  - Agent Settings page — profile selector + Install button, accessible anytime post-install
  - Skills page banner — shown when no profile is set, contextual prompt to configure
- Install profiles: `none` / `basic` / `standard` (default) / `full`
  - `basic`: python-docx, pypdf, pillow
  - `standard`: + reportlab, python-pptx, beautifulsoup4, lxml, tabulate, httpx
  - `full`: + pandas, pydantic, python-dateutil, chardet
- Covers most document and data skills from skills.sh
- Gated by `skill_execution_enabled: 1` in `site_config.json`

**Phase 3 — Container execution**
- Full isolated container per run (local Docker socket, remote Docker over TLS, or managed service: E2B/Modal)
- Execution backend abstracted — `skill_execution_mode` in site_config routes to the right backend
- `pip install` at runtime inside container, full filesystem, network with SSRF protection
- Pre-warmed images keyed by package set — build once, reuse across executions
- Every skills.sh skill works
- Local Docker: `skill_execution_mode: local_docker`, `skill_docker_socket: /var/run/docker.sock`
- Remote Docker: `skill_execution_mode: remote_docker` + TLS cert config
- Managed: `skill_execution_mode: e2b` + API key in Agent Settings

### skills.sh Compatibility

The docx skill (and most skills.sh skills) tell the agent to write Python code and execute it. With Phase 2+:
1. Fetch `SKILL.md` → store as Skill instructions
2. Attach `run_python` tool to the skill
3. Agent reads instructions, generates code, calls `run_python`, gets the file back

The SKILL.md works as-is. No manual porting needed from Phase 2 onward. Node.js skills follow the same pattern via `run_node`.

---

## Distribution

- `tridz-dev/huf-skills` — official curated repo
- GitHub import — any public repo with `_index.json` manifest
- Direct `.huf` file upload via UI
- Future: signed packages for marketplace trust

---

## What Needs to Be Built

### Backend

- `huf/ai/skills/` package
  - `loader.py` — dynamic module loading, tool/knowledge/prompt merging into agents
  - `importer.py` — `.huf` zip parsing, fixture import, tool registration
  - `github.py` — GitHub API fetch, `_index.json` parsing, raw file download
  - `exporter.py` — package a Skill doc + linked resources into `.huf` zip
  - `node_executor.py` — controlled Node.js subprocess for JS tools
  - `deps.py` — dependency checker, missing package warnings
  - `api.py` — whitelisted endpoints for UI
- New DocTypes: `Skill`, `Agent Skill` (child table on Agent), `Skill Category`
- Extend `Agent Tool Function` with `Script` and `Node` source types
- Wire `AgentManager` to merge skill tools/knowledge/instructions at agent construction
- Update `huf/hooks.py` — skill sync on `after_migrate`, `after_app_install`

### Frontend

- Skills marketplace page — browse, search, install from GitHub or upload `.huf`
- Skill form page — create/edit, link tools/knowledge/prompts, export button
- Skills tab on Agent form — attach skills with Mandatory/Optional mode
- Import modal — GitHub URL or file upload, shows dependency warnings
- Sidebar entry and routes

### Skill Package Format

- Define `manifest.json` schema
- Define `_index.json` registry schema for skill repos
- Publish `tridz-dev/huf-skills` repo with 3–5 starter skills (PDF, HTTP, Data)

---

## Decisions Still Open

| Question | Options |
|----------|---------|
| Optional skill behaviour | Pre-load all tools, gate via system prompt preamble (v1) vs dynamic load mid-conversation (not feasible with current SDK) |
| Skill versioning on agents | Live Skill doc (v1) vs lock version at attach time |
| Code signing | Trust-on-install (v1) vs GPG-signed packages for marketplace |
| Node.js scope | Subprocess only (v1) vs dedicated Node service |
| Skill scope | Site-level (v1) vs workspace-level |

---

## Phase Suggestion

1. **Phase 1 — Packaging & distribution.** Skills bundle existing tools/knowledge/prompts, export/import as `.huf`, install from GitHub. No code execution. Establishes format, UX, and the `huf-skills` repo with 3–5 pre-built skills using existing Huf tools.

2. **Phase 2 — Restricted execution + package management.** Add `run_python` / `run_node` tools via RestrictedPython. Packages installed at skill install time from a trusted list (not at runtime). Setup wizard step + Agent Settings + Skills page banner for package setup. Install profiles (basic / standard / full) with sensible defaults. Most skills.sh document and data skills work.

3. **Phase 3 — Container execution + marketplace.** Full isolated containers with runtime `pip install`. Backend abstracted: local Docker socket, remote Docker over TLS, or managed service (E2B/Modal) — all driven by site_config. Pre-warmed images per package set. `tridz-dev/huf-skills` curated registry with one-click install. Optional code signing. Every skills.sh skill works.
