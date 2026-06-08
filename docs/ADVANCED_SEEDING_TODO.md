# TODO: Advanced App Agent Seeding

The current App Agent Seeding system correctly imports flat JSON records for Agents, Tools, Prompts, Knowledge Sources, and Triggers. However, complex capabilities like SQLite databases for knowledge, complex prompt bodies, and graphical workflow definitions require handling files and binary assets alongside the JSON metadata.

This document outlines the detailed plan to expand the `huf/` seeding directory to support these advanced types using the exact same declarative pattern.

## 1. SQLite FTS & Vector Knowledge Sources (Pre-built vs Raw)

Currently, `Knowledge Source` JSONs are imported, but if the `storage_mode` is `SQLite (FTS)` or `SQLite (Vector)`, the actual `.sqlite` file is missing. Furthermore, we need to support importing raw, un-indexed documents (PDFs, Word docs, Markdown) that must be ingested by the system after seeding.

### Plan
Allow apps to include `.sqlite` files (for pre-indexed DBs) or raw documents (like `.pdf`, `.docx`) directly in their `huf/knowledge/` folder alongside the JSON definition.

### Folder Structure
```text
myapp/huf/knowledge/
  sales_playbook.json
  sales_playbook.sqlite  <-- The pre-built SQLite DB
  hr_policies.json
  hr_policies.pdf        <-- A raw document to be ingested
```

### Implementation Steps
1. **Scanner Update (`huf/ai/app_seeding/scanner.py`)**:
   - Update `get_seed_files` to also detect `.sqlite`, `.pdf`, `.docx`, `.md`, and `.txt` files alongside JSON.
2. **Loader Update (`huf/ai/app_seeding/loaders.py`)**:
   - In `upsert_knowledge()`, check if a corresponding file (e.g., `source_name.sqlite` or `source_name.pdf`) exists in the same directory as the JSON.
   - **For pre-indexed `.sqlite` files**:
     - Copy the `.sqlite` file into Frappe's `site/public/files/knowledge/` directory.
     - Update the `Knowledge Source` document's `sqlite_file` and `sqlite_file_path` fields.
     - Calculate and update the `index_size_bytes`.
   - **For raw non-ingested documents (.pdf, .docx, etc.)**:
     - Upload the file to Frappe using `frappe.get_doc({"doctype": "File", ...})` and attach it to the `Knowledge Source` document via a `Knowledge Input` record.
     - Trigger the background ingestion queue (`huf.ai.knowledge.enqueue_index_job` or similar) so the document is parsed, chunked, and embedded/indexed asynchronously after seeding.
3. **Seeder Update (`huf/ai/app_seeding/seeder.py`)**:
   - Pass the `huf_dir` path down to the loaders so they can resolve adjacent files.

---

## 2. Prompt Templates as Markdown/Text

Writing large, multi-line prompts inside a JSON string is error-prone and breaks IDE syntax highlighting.

### Plan
Allow apps to define the `prompt_body` in a sidecar `.md` or `.txt` file, keeping the `.json` strictly for metadata.

### Folder Structure
```text
myapp/huf/prompts/
  lead_summary.json
  lead_summary.md  <-- Contains the actual prompt text
```

### Implementation Steps
1. **Loader Update (`huf/ai/app_seeding/loaders.py`)**:
   - In `upsert_prompt()`, check if a `.md` or `.txt` file exists with the same base name as the JSON.
   - If it exists, read its contents.
   - Inject the contents into the `prompt_body` field of the data payload before upserting the `Agent Prompt` DocType.

---

## 3. Workflows (Flows)

HUF Flows (likely `Agent Flow` or similar DocType) contain graphical node-based representations or complex execution JSONs. 

### Plan
Support a `huf/flows/` directory to seed these complex workflow definitions.

### Folder Structure
```text
myapp/huf/flows/
  lead_routing_flow.json
```

### Implementation Steps
1. **Schema Check**:
   - Ensure the Flow DocType has `source_app` and `source_file` provenance fields added via schema.
2. **Scanner & Seeder Updates**:
   - Add `"flows"` to the `LOAD_ORDER` in `seeder.py` (likely loaded before triggers, after tools/agents).
3. **Loader Update (`huf/ai/app_seeding/loaders.py`)**:
   - Create `upsert_flow(data, source_app, source_file)`.
   - Workflows often have nested nodes or edges. If these are child tables, the Frappe `doc.update()` will handle them automatically if formatted correctly in the JSON.
   - If the flow uses a distinct JSON format for its canvas (e.g., a `flow_data` JSON field), the exporter must stringify it properly, and the loader must inject it.

---

## 4. Universal Exporter Updates

To ensure developers can easily create these advanced seeds:
1. **Update `exporter.py`**:
   - `export_knowledge_to_seed`: If it's a SQLite knowledge source, zip or copy the `.sqlite` file alongside the exported JSON.
   - `export_prompt_to_seed`: Automatically extract the `prompt_body` into a `.md` file and remove it from the exported `.json` metadata.
   - Add `export_flow_to_seed`: Serialize the flow document.

## 5. Security & Validation

- **SQLite Validation**: Before copying a `.sqlite` file, verify its magic bytes (`SQLite format 3\000`) to prevent malicious file uploads.
- **Size Limits**: Enforce maximum file size limits for seeded SQLite databases to prevent repo bloat and migration timeouts.
