> ⚠️ This is a **draft** feature. Test on a development site and run `bench migrate` after switching to the `feature/skills-system` branch.

# Skills System — Testing Guide

## 1. Setup

### 1.1 Switch the Huf app to the feature branch

```bash
# If you have a local clone of huf
cd /path/to/huf
git fetch origin
git checkout feature/skills-system
```

In your Frappe bench, the `apps/huf` directory should point to this branch.

### 1.2 Migrate the site

```bash
bench --site development.localhost migrate
bench --site development.localhost clear-cache
```

This creates the new DocTypes and seeds default Skill Categories (`General`, `CRM`, `Support`).

### 1.3 Build frontend assets

```bash
cd apps/huf/frontend
yarn install
yarn build
```

Or, for live development:

```bash
yarn dev
```

---

## 2. Manual UI test — create a Skill

1. Log in to Huf Desk and open **Skills** from the sidebar.
2. Click **New Skill**.
3. Fill in:
   - **Skill Name:** `test-sales-skill`
   - **Title:** `Test Sales Skill`
   - **Description:** `Helps with sales orders and leads.`
   - **Category:** `CRM`
   - **Instructions:** `When the user asks about sales, prefer CRM tools and knowledge.`
4. In the **Tools** tab, add an existing `Agent Tool Function` (e.g. `get_sales_orders` if available).
5. In the **Knowledge** tab, add an existing `Knowledge Source` with mode `Mandatory`.
6. Save.

Expected: Skill is created with status **Active**.

---

## 3. Attach a Skill to an Agent

1. Open an existing Agent or create a new one.
2. Go to the **Skills** tab.
3. Click **Add Skill**, select `test-sales-skill`.
4. Set **Mode** to `Mandatory`.
5. Save the agent.

Expected: The `Agent Skill` child table row is persisted.

---

## 4. Runtime test — mandatory skill

1. Open the Agent Chat or Agent Console for the agent.
2. Send a prompt related to the skill (e.g. "tell me about sales").
3. Inspect the response / tool usage.

Expected:
- The skill's system instructions appear in the agent prompt.
- The skill's tools are available to the agent.
- Mandatory skill knowledge is injected into the context.

You can also check the created **Agent Run** record to see which tools/knowledge were used.

---

## 5. Optional skill test

1. Create or use a Skill with mode `Optional` on the Agent.
2. Chat with the agent.

Expected:
- The system prompt lists the optional skill with its description.
- The `list_skills` tool is available and returns the optional skill list.
- The optional skill's tools are already loaded; the agent should invoke them only when the request matches.

> Note: Dynamic `load_skill` is **not** implemented in v1. Optional skills are pre-loaded and gated by the prompt.

---

## 6. Import from Git

### 6.1 Prepare a test repo

Create a repo with a `skills/` directory containing `skill.json`:

```json
{
  "name": "huf-test-git-skill",
  "title": "Huf Test Git Skill",
  "description": "Imported skill for testing.",
  "category": "General",
  "version": "1.0.0",
  "instructions": "Use this skill when testing imports.",
  "tools": ["get_sales_orders"],
  "knowledge": [{"source": "Test Source", "mode": "Mandatory"}]
}
```

Push it to a public GitHub repo.

### 6.2 Import via UI

1. In Huf, go to **Skills**.
2. Click **Import from Git**.
3. Enter:
   - **Repo URL:** `https://github.com/<user>/<repo>`
   - **Path:** `skills`
   - **Ref:** `main`
4. Submit.

Expected: A new Skill doc is created. Any missing tool/knowledge references are skipped and warnings are logged in **Error Log**.

### 6.3 Import via API

```bash
bench --site development.localhost execute huf.ai.skills.api.import_skill_from_git --kwargs '{"repo_url": "https://github.com/<user>/<repo>", "path": "skills", "ref": "main"}'
```

---

## 7. App-provided skills via `huf_skills` hook

### 7.1 Add a hook

In another installed Frappe app, edit `hooks.py`:

```python
huf_skills = [
    {
        "skill_name": "my_app_skill",
        "title": "My App Skill",
        "description": "Skill provided by my app.",
        "function_path": "my_app.skills.manifest.get_skill_definition",
    }
]
```

Create `my_app/skills/manifest.py`:

```python
def get_skill_definition():
    return {
        "name": "my_app_skill",
        "title": "My App Skill",
        "description": "Skill provided by my app.",
        "category": "General",
        "instructions": "Use this skill for my app tasks.",
        "tools": ["my_app_tool"],
    }
```

### 7.2 Sync

```bash
bench --site development.localhost execute huf.ai.skills.hooks.sync_app_skills --kwargs '{"use_cache": false}'
```

Expected: A Skill named `my_app_skill` is created/updated with `source_type` = `App Provided` and `provider_app` = `my_app`.

---

## 8. Backend smoke tests

### 8.1 List skills attached to an agent

```python
from huf.ai.skills.loader import get_agent_skills
print(get_agent_skills("My Agent"))
```

### 8.2 Load skill tools

```python
from huf.ai.skills.loader import load_all_skill_tools
agent = frappe.get_doc("Agent", "My Agent")
print(load_all_skill_tools(agent, frappe.session.user))
```

### 8.3 Knowledge search across skill sources

Call the agent's `knowledge_search` tool without specifying a `knowledge_source`. It should search all agent-level and skill-attached sources.

---

## 9. Expected limitations (v1)

- `load_skill` dynamic tool loading is not implemented.
- Skill version-locking on agents is not implemented.
- Workspace-scoped skills are not implemented.
- Manifest imports skip broken links instead of creating stubs.
- Common destination import relies on `Agent Settings.skill_destinations` or the default `tridz-dev/huf-skills`.

---

## 10. Rollback

```bash
bench --site development.localhost uninstall-app huf
# or, if you want to keep huf but remove skill test data:
bench --site development.localhost execute frappe.delete_doc_if_exists --kwargs '{"doctype": "Skill", "name": "test-sales-skill"}'
```

Then switch back to `develop` and migrate.
