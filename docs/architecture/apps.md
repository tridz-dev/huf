# App Seeding Framework

HUF discovers and loads resources bundled inside *other* installed Frappe apps — prompts, tools, knowledge sources, agents, triggers, and launcher-app manifests — from flat JSON files under each app's `huf/` folder, and upserts them into the matching HUF DocTypes. It is a discovery/loading mechanism for pre-authored resource definitions shipped in app source trees, not a code- or app-generation system: nothing here writes Frappe app code, DocTypes, or Python from natural language.

Note on provenance: an earlier large draft PR (#549) described this subsystem as "generating Frappe applications and code from natural language." That characterization does not match the code and should not be treated as a description of this framework. The actual mechanism is the JSON-seed loader described below, plus (separately) an LLM-callable "hub builder" tool set that can create `Agent`/`Agent Tool Function`/table records through normal DocType APIs at chat time — see `BUILDER_TOOL_NAMES` in `huf/ai/app_seeding/hub_orchestrator.py:57`, which is unrelated to the seeding scan.

## How discovery works

`find_seed_dirs()` scans every installed app (skipping `huf` itself) for a `huf/` directory, checking two candidate locations per app:

1. The Python package root, e.g. `apps/myapp/myapp/huf/`
2. The app repo root, e.g. `apps/myapp/huf/`

Source: `huf/ai/app_seeding/scanner.py:5-30`.

Within a discovered `huf/` directory, `get_seed_files(huf_dir, type_folder)` does a **non-recursive** scan of one subfolder, collecting every `*.json` file (`huf/ai/app_seeding/scanner.py:32-49`). Each JSON file may contain either a single object or a JSON list of objects — both are accepted (`huf/ai/app_seeding/seeder.py:51`).

## Seed folders and resource types

| Folder | Loader | Target DocType | Key field |
|---|---|---|---|
| `prompts/` | `upsert_prompt` | `Agent Prompt` | `title` |
| `tools/` | `upsert_tool` | `Agent Tool Function` | `tool_name` |
| `knowledge/` | `upsert_knowledge` | `Knowledge Source` | `source_name` |
| `agents/` | `upsert_agent` | `Agent` | `agent_name` |
| `triggers/` | `upsert_trigger` | `Agent Trigger` | `trigger_name` |
| `apps/` | `upsert_huf_app` | `HUF App` | `app_id` |

Source: `LOAD_ORDER` in `huf/ai/app_seeding/seeder.py:28-35`, loader bodies in `huf/ai/app_seeding/loaders.py:129-189` and `huf/ai/app_seeding/apps_loader.py:273-350`.

The old AGENTS.md text listed only five folders (`prompts/`, `tools/`, `knowledge/`, `agents/`, `triggers/`); the current code adds a sixth, `apps/`, for launcher-app manifests registered in the `HUF App` DocType (`huf/huf/doctype/huf_app/`). This folder did not exist when the original summary was written and should be treated as current, not legacy.

`LOAD_ORDER` is deliberately sequenced — prompts, tools, knowledge, and agents load before triggers, and `apps` loads last, so a manifest can reference agents/tools seeded earlier in the same run (comment at `huf/ai/app_seeding/seeder.py:25-27`).

## Generic seed loading (`seed_app` / `seed_all`)

`seed_app(app_name, huf_dir)` iterates `LOAD_ORDER`, reads each JSON seed file per folder, and calls the matching loader per item (`huf/ai/app_seeding/seeder.py:37-85`). Each loader ultimately calls `_upsert_doc` (`huf/ai/app_seeding/loaders.py:99-127`), which:

- Looks up an existing document by the type's key field.
- Validates any `Link`, `Dynamic Link`, and `Table MultiSelect` field values against existing documents (`_validate_link_refs`, `huf/ai/app_seeding/loaders.py:30-96`); a seed item referencing a missing record is skipped with a `missing_refs` error rather than failing the whole run.
- Stamps `source_app` and `source_file` onto the document for provenance.
- Inserts or updates with `ignore_permissions=True`.

`seed_all()` calls `find_seed_dirs()` and runs `seed_app` for every discovered app, collecting a `SeedResult` (seeded/skipped counts, error list, skipped-record detail) per app (`huf/ai/app_seeding/seeder.py:87-96`).

Type-specific notes in the loaders (`huf/ai/app_seeding/loaders.py`):
- `upsert_agent` maps a seed's `tools`/`knowledge` list fields onto the `agent_tool`/`agent_knowledge` child tables.
- `upsert_tool` falls back to `types: "App Provided"` for any `types` value outside the known `VALID_TYPES` list, and auto-creates a missing `Agent Tool Type` row when `tool_type` is set.
- `upsert_knowledge` remaps legacy `storage_mode` values (`"SQLite (FTS)"`, `"SQLite (Vector)"`) onto the current `storage_mode`/`knowledge_type` schema.

## `apps/` manifests: a stricter second pass

The `apps/` folder is seeded twice: once loosely through the generic `LOAD_ORDER` pass above (link-ref validation only), and again through a dedicated, stricter sync in `huf/ai/app_seeding/apps_loader.py`:

- `validate_manifest()` enforces the full MVP manifest grammar — required `manifest_version` (must equal `SUPPORTED_MANIFEST_VERSION = 1`), `app_id` matching `^[a-z][a-z0-9_\-]*$`, a site-local `route`, an optional site-local or simple-identifier `icon`, `launch_mode` fixed to `"route"`, and an `exposed_tables` list capped at 20 entries (`apps_loader.py:181-264`).
- `_validate_exposed_tables()` additionally confirms each exposed DocType exists and is owned (via its Module Def) by the same provider app, rejecting cross-app table exposure (`apps_loader.py:157-171`).
- `upsert_huf_app()` computes a `manifest_hash` (sha256 over the normalized manifest) and skips the write entirely when nothing changed; on update it never overwrites a manually-set `enabled` flag ("manual-disable-wins", `apps_loader.py:340-345`).
- A duplicate `app_id` claimed by a different provider app is rejected and logged as a `HUF App Registration Collision`, without touching the existing valid registration (`apps_loader.py:306-316`).
- Invalid manifests are still recorded in the registry (`sync_status="Invalid"`) when they carry a usable `app_id`, so a System Manager can see what failed and why (`_record_invalid_manifest`, `apps_loader.py:353-399`).
- `sync_huf_apps()` runs the full cycle — discover, upsert valid manifests, record invalid ones, then `cleanup_orphaned_apps()` deletes any `HUF App` record whose provider app was uninstalled or whose source file disappeared (`apps_loader.py:402-499`).
- `on_app_uninstalled(app_name)` removes all `HUF App` registry rows owned by that app on `after_app_uninstall` (`apps_loader.py:502-519`).

## Triggers: when seeding runs

| Trigger point | Hook / entry point | What runs |
|---|---|---|
| App installation | `after_app_install` → `huf.ai.app_seeding.seeder.on_app_installed` | Seeds just the newly installed app's `huf/` folder via `seed_app` |
| Migration | `after_migrate` → `huf.install.after_migrate` | Full `seed_all()` across every installed app, then `sync_huf_apps()` |
| Manual (UI/API) | `@frappe.whitelist()` `seed_all_apps` | Full `seed_all()` across every installed app; requires `System Manager` role |

Sources: hook registration in `huf/hooks.py:114-121`; `after_migrate` orchestration in `huf/install.py:153-208` (calls `seed_all()` at `huf/install.py:188-189`, then `sync_huf_apps()` at `huf/install.py:201-202`); manual entry point in `huf/ai/app_seeding/seeder.py:110-124`.

The old AGENTS.md excerpt described these three triggers correctly; that part of the summary still holds. What it omitted is that `after_migrate` also runs a full `HUF App` manifest sync (`sync_huf_apps`) immediately after the generic seed pass, and that `after_app_install`'s immediate seeding (`on_app_installed`) only seeds the one app being installed, not a full rescan.

## Adjacent but distinct: tool registry sync

Seeded tools (`tools/*.json`, type `App Provided`) are separate from HUF's other tool-discovery mechanism, the `tool_registry` module, which scans installed apps' `huf_tools` hook functions in Python (not JSON) to register dynamically-provided tools — see `sync_discovered_tools` / `sync_app_tools` in `huf/ai/tool_registry.py`. Both run during `after_migrate`, and tool sync runs before app seeding so that agent seeds referencing hook-provided tools resolve correctly (`huf/install.py:176-193`; comment at `huf/ai/app_seeding/hub_orchestrator.py:53-54`).

## Testing

Backend test coverage for this framework lives in `huf/ai/app_seeding/tests/test_seed_fk.py` (link-ref validation, `seed_app`/`seed_all_apps` behavior) and `huf/ai/app_seeding/tests/test_apps_sync.py` (manifest validation, collision handling, orphan cleanup).

## See also

`docs/reference/doctypes.generated.md` for full field listings of `HUF App`, `Agent`, `Agent Tool Function`, `Knowledge Source`, `Agent Prompt`, and `Agent Trigger`.
