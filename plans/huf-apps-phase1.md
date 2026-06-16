# Huf Apps — Phase 1 Build Spec

## What This Is

A system where a user describes a work application in plain language ("I'm a student counselor and want to track my students") and Huf generates a fully functional, AI-enabled mini-app: custom data tables, a pre-configured agent with CRUD tools, optional knowledge, and a rendered UI shell — all without writing code.

The user interacts with a "Planner" chat agent. When they confirm, the agent calls `install_huf_app` which wires everything together. The app is then launchable from an App Registry page.

## Architecture Overview

```
User (chat) → App Planner Agent → install_huf_app() →
  ├── HUF Tables (schema)
  ├── Agent Tool Functions (CRUD per table)
  ├── Agent (instructions + tools + knowledge)
  ├── Knowledge Sources + Inputs (optional)
  └── Huf App record (manifest + metadata)
                ↓
App Registry page → Launch → App Shell (chat | dashboard | list)
```

---

## Manifest Schema

All installer behavior is driven by this JSON. The planner agent generates it; the installer consumes it.

```json
{
  "app_id": "student-counselor",
  "label": "Student Counselor",
  "description": "Track student progress and counseling sessions",
  "icon": "Users",

  "tables": [
    {
      "table_name": "Student",
      "description": "Student records",
      "fields": [
        {"fieldname": "student_name", "label": "Name",   "fieldtype": "Data",   "reqd": 1, "in_list_view": 1},
        {"fieldname": "grade",        "label": "Grade",  "fieldtype": "Select", "options": "9\n10\n11\n12", "in_list_view": 1},
        {"fieldname": "status",       "label": "Status", "fieldtype": "Select", "options": "at_risk\non_track\nexcelling", "in_list_view": 1},
        {"fieldname": "notes",        "label": "Notes",  "fieldtype": "Long Text"}
      ]
    },
    {
      "table_name": "Counseling Session",
      "description": "Session notes per student",
      "fields": [
        {"fieldname": "student",   "label": "Student",      "fieldtype": "Link",  "options": "HF Student", "reqd": 1, "in_list_view": 1},
        {"fieldname": "date",      "label": "Session Date", "fieldtype": "Date",  "reqd": 1, "in_list_view": 1},
        {"fieldname": "notes",     "label": "Notes",        "fieldtype": "Long Text"},
        {"fieldname": "progress",  "label": "Progress",     "fieldtype": "Select","options": "improving\nstable\nregressing", "in_list_view": 1}
      ]
    }
  ],

  "agent": {
    "agent_name": "Counselor Assistant",
    "instructions": "You help school counselors track student progress. Answer questions about students and sessions. Suggest interventions based on patterns. When asked to create, update, or find records, use the available tools.",
    "model": "gpt-4o",
    "provider": "OpenAI"
  },

  "knowledge": [
    {
      "source_name": "Counseling Best Practices",
      "knowledge_type": "sqlite_fts",
      "inputs": [
        {"input_type": "Text", "text": "Student counseling best practices include..."}
      ]
    }
  ],

  "shell": "dashboard",

  "nav": [
    {"label": "All Students",  "table": "Student",           "view": "grid",  "filter": []},
    {"label": "At-Risk",       "table": "Student",           "view": "list",  "filter": [["status", "=", "at_risk"]]},
    {"label": "Sessions",      "table": "Counseling Session","view": "list",  "filter": []},
    {"label": "Ask Assistant", "type": "chat"}
  ],

  "views": [
    {
      "table": "Student",
      "collection_layout": "grid",
      "card_variant": "summary-first",
      "list_fields": ["student_name", "grade", "status"],
      "record_view": "view"
    },
    {
      "table": "Counseling Session",
      "collection_layout": "list",
      "card_variant": "data-first",
      "list_fields": ["student", "date", "progress"],
      "record_view": "view"
    }
  ]
}
```

**Field rules (enforced by installer):**
- `app_id`: kebab-case, unique across all Huf Apps
- `tables[].fields[].fieldtype`: must be one of the allowed HUF field types (Data, Small Text, Text, Long Text, Int, Float, Currency, Percent, Check, Date, Datetime, Time, Duration, Select, Link, Rating, Color, Phone)
- `tables[].fields[].options`: required when fieldtype = "Select" (newline-separated values) or "Link" (target DocType name, e.g. "HF Student")
- `agent.model` + `agent.provider`: optional; fallback logic resolves at install time
- `shell`: one of `"chat"`, `"dashboard"`, `"list"`
- `nav[].type`: `"collection"` (default) or `"chat"`. Collection items require `table` + `view`.
- `views[].collection_layout`: one of `"grid"`, `"list"`, `"table"`
- `views[].card_variant`: one of `"summary-first"`, `"data-first"`
- `views[].record_view`: one of `"form"`, `"view"`

---

## Files to Create / Modify

### Backend (Python)

#### 1. `huf/ai/app_installer.py` — NEW

Purpose: Single whitelisted entry point. Validates manifest, calls HUF Table API, creates Agent Tool Functions, creates Agent, creates Knowledge Sources, saves Huf App record.

```python
import frappe
from huf.huf.doctype.huf_data_table.api import create_data_table

@frappe.whitelist()
def install_huf_app(manifest: str) -> dict:
    """
    Install a Huf App from a JSON manifest.
    Returns {"success": True, "app_id": "...", "agent": "...", "tables_created": [...]}
    """
    data = frappe.parse_json(manifest)
    _validate_manifest(data)

    app_id = data["app_id"]
    if frappe.db.exists("Huf App", app_id):
        frappe.throw(f"App '{app_id}' already installed.")

    # Step 1: Create HUF tables
    table_map = {}  # {"Student": "HF Student"}
    for tdef in data.get("tables", []):
        result = create_data_table(
            table_name=tdef["table_name"],
            fields=tdef["fields"],
            description=tdef.get("description", ""),
        )
        doctype_name = result["data"]["doctype_name"]  # e.g. "HF Student"
        table_map[tdef["table_name"]] = doctype_name

    # Step 2: Create Agent Tool Functions (5 CRUD ops per table)
    tool_names = _create_crud_tools(app_id, table_map)

    # Step 3: Resolve model + provider
    provider, model = _resolve_model(data.get("agent", {}))

    # Step 4: Create Agent
    agent_def = data["agent"]
    agent_doc = frappe.get_doc({
        "doctype": "Agent",
        "agent_name": agent_def["agent_name"],
        "provider": provider,
        "model": model,
        "instructions": agent_def["instructions"],
        "allow_chat": 1,
        "persist_conversation": 1,
    })
    for tool_name in tool_names:
        agent_doc.append("agent_tool", {"tool": tool_name})
    agent_doc.insert(ignore_permissions=True)

    # Step 5: Create Knowledge Sources + Inputs; link to agent
    for ks_def in data.get("knowledge", []):
        ks_doc = frappe.get_doc({
            "doctype": "Knowledge Source",
            "source_name": ks_def["source_name"],
            "knowledge_type": ks_def.get("knowledge_type", "sqlite_fts"),
            "scope": "Site",
        })
        ks_doc.insert(ignore_permissions=True)
        for inp in ks_def.get("inputs", []):
            frappe.get_doc({
                "doctype": "Knowledge Input",
                "knowledge_source": ks_doc.name,
                "input_type": inp["input_type"],
                "text": inp.get("text", ""),
                "file": inp.get("file", ""),
                "url": inp.get("url", ""),
            }).insert(ignore_permissions=True)
        agent_doc.reload()
        agent_doc.append("agent_knowledge", {
            "knowledge_source": ks_doc.name,
            "mode": "Optional",
            "max_chunks": 5,
        })
        agent_doc.save()

    # Step 6: Create Huf App record
    frappe.get_doc({
        "doctype": "Huf App",
        "app_id": app_id,
        "label": data["label"],
        "description": data.get("description", ""),
        "icon": data.get("icon", ""),
        "shell": data["shell"],
        "agent": agent_doc.name,
        "manifest_json": frappe.as_json(data),
        "status": "Active",
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {
        "success": True,
        "app_id": app_id,
        "agent": agent_doc.name,
        "tables_created": list(table_map.keys()),
    }


def _create_crud_tools(app_id: str, table_map: dict) -> list[str]:
    """Create one Agent Tool Function per CRUD operation per table. Returns list of tool names."""
    ops = [
        ("Get Document",    "Fetch a single {t} record by name"),
        ("Get List",        "List {t} records with optional filters"),
        ("Create Document", "Create a new {t} record"),
        ("Update Document", "Update fields on an existing {t} record"),
        ("Delete Document", "Delete a {t} record by name"),
    ]
    names = []
    for table_name, doctype_name in table_map.items():
        slug = table_name.lower().replace(" ", "_")
        for op_type, desc_tpl in ops:
            tool_name = f"app_{app_id}_{slug}_{op_type.lower().replace(' ', '_')}"
            if not frappe.db.exists("Agent Tool Function", tool_name):
                frappe.get_doc({
                    "doctype": "Agent Tool Function",
                    "tool_name": tool_name,
                    "types": op_type,
                    "reference_doctype": doctype_name,
                    "description": desc_tpl.format(t=table_name),
                }).insert(ignore_permissions=True)
            names.append(tool_name)
    return names


def _resolve_model(agent_def: dict) -> tuple[str, str]:
    """
    Returns (provider_name, model_name).
    Priority:
      1. manifest provider + model if provider key exists in AI Provider
      2. first AI Provider with a non-empty api_key
      3. frappe.throw() asking user to add a provider key
    """
    requested_provider = agent_def.get("provider")
    requested_model = agent_def.get("model")

    if requested_provider and requested_model:
        if frappe.db.get_value("AI Provider", requested_provider, "api_key"):
            return requested_provider, requested_model

    # Fall back to any available provider
    providers = frappe.get_all("AI Provider", filters={"disabled": 0}, fields=["name", "api_key"])
    for p in providers:
        if p.get("api_key"):
            # Pick first model from this provider
            model = frappe.get_value("AI Model", {"provider": p["name"], "disabled": 0}, "name")
            if model:
                return p["name"], model

    frappe.throw(
        "No AI provider key found. Go to AI Providers and add an API key before installing apps."
    )


def _validate_manifest(data: dict):
    required = ["app_id", "label", "tables", "agent", "shell", "views"]
    for field in required:
        if not data.get(field):
            frappe.throw(f"Manifest missing required field: '{field}'")
    valid_shells = ("chat", "dashboard", "list")
    if data["shell"] not in valid_shells:
        frappe.throw(f"shell must be one of: {valid_shells}")


@frappe.whitelist()
def delete_huf_app(app_id: str) -> dict:
    """
    Remove a Huf App and its agent. Does NOT delete HUF tables or their data.
    Returns {"success": True}
    """
    app = frappe.get_doc("Huf App", app_id)
    if app.agent:
        frappe.delete_doc("Agent", app.agent, ignore_permissions=True)
    frappe.delete_doc("Huf App", app_id, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def get_huf_app(app_id: str) -> dict:
    """Return full manifest JSON for a Huf App."""
    doc = frappe.get_doc("Huf App", app_id)
    return frappe.parse_json(doc.manifest_json)
```

---

#### 2. `huf/ai/app_tools.py` — NEW

Purpose: Registers `install_huf_app` as a tool callable by the App Planner agent via `huf_tools` hook.

```python
from huf.ai.app_installer import install_huf_app as _install

HUF_APP_TOOLS = [
    {
        "name": "install_huf_app",
        "description": (
            "Install a Huf App from a JSON manifest. Call this when the user has confirmed "
            "the app design and wants to build it. Returns the installed app_id and agent name."
        ),
        "function": _install,
        "parameters": {
            "manifest": {
                "type": "string",
                "description": "The full app manifest as a JSON string matching the Huf App manifest schema.",
                "required": True,
            }
        },
    }
]
```

---

#### 3. `huf/hooks.py` — MODIFY

Add `app_tools.HUF_APP_TOOLS` to the `huf_tools` list:

```python
# Existing entry (example):
# huf_tools = ["huf.ai.flow_tools.FLOW_TOOLS"]
# Add:
huf_tools = [
    "huf.ai.flow_tools.FLOW_TOOLS",
    "huf.ai.app_tools.HUF_APP_TOOLS",   # ← add this line
]
```

Exact line to find: search for `huf_tools` in `huf/hooks.py` and append the new entry.

---

#### 4. `huf/huf/doctype/huf_app/` — NEW DocType

Create four files:

**`huf/huf/doctype/huf_app/__init__.py`** — empty file.

**`huf/huf/doctype/huf_app/huf_app.py`**:
```python
import frappe
from frappe.model.document import Document

class HufApp(Document):
    pass
```

**`huf/huf/doctype/huf_app/huf_app.json`**:
```json
{
  "name": "Huf App",
  "module": "Huf",
  "doctype": "DocType",
  "is_submittable": 0,
  "track_changes": 0,
  "fields": [
    {"fieldname": "app_id",       "fieldtype": "Data",      "label": "App ID",       "reqd": 1, "unique": 1, "in_list_view": 1},
    {"fieldname": "label",        "fieldtype": "Data",      "label": "Label",        "reqd": 1, "in_list_view": 1},
    {"fieldname": "description",  "fieldtype": "Small Text","label": "Description"},
    {"fieldname": "icon",         "fieldtype": "Data",      "label": "Icon"},
    {"fieldname": "shell",        "fieldtype": "Select",    "label": "Shell",
      "options": "chat\ndashboard\nlist",                   "reqd": 1, "in_list_view": 1},
    {"fieldname": "agent",        "fieldtype": "Link",      "label": "Agent",        "options": "Agent"},
    {"fieldname": "manifest_json","fieldtype": "JSON",      "label": "Manifest JSON"},
    {"fieldname": "status",       "fieldtype": "Select",    "label": "Status",
      "options": "Active\nDisabled",                        "default": "Active", "in_list_view": 1}
  ],
  "autoname": "field:app_id",
  "title_field": "label",
  "permissions": [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
  ]
}
```

**`huf/huf/doctype/huf_app/huf_app_list.json`** — empty `{}` (default list view).

---

#### 5. `huf/install.py` — MODIFY

Add an "App Planner" agent that is created once at install. Find the section where agents are seeded (or add a new `create_app_planner_agent()` call at the bottom of `after_install()`).

```python
def create_app_planner_agent():
    if frappe.db.exists("Agent", "App Planner"):
        return

    # Resolve any available provider
    providers = frappe.get_all("AI Provider", filters={"disabled": 0}, fields=["name"])
    if not providers:
        return  # No provider yet — agent will be created when first provider is added
    provider = providers[0]["name"]
    model = frappe.get_value("AI Model", {"provider": provider, "disabled": 0}, "name")
    if not model:
        return

    doc = frappe.get_doc({
        "doctype": "Agent",
        "agent_name": "App Planner",
        "provider": provider,
        "model": model,
        "allow_chat": 1,
        "persist_conversation": 1,
        "instructions": """You are the Huf App Builder. Help users design and build work applications.

PROCESS:
1. Ask: What work do you do, and what do you need to track?
2. Propose a schema (2-4 tables, 4-8 fields each). Show it clearly.
3. Ask for feedback and iterate until confirmed.
4. Summarize what the app will include: tables, fields, nav, shell type.
5. Ask: "Ready to build this app?"
6. When the user confirms, call install_huf_app with the complete manifest JSON.

MANIFEST RULES:
- app_id: kebab-case from the label, e.g. "student-counselor"
- shell: "chat" if the workflow is conversational; "dashboard" if they check status daily; "list" for simple CRUD
- For each table, mark fields used for display with "in_list_view": 1 (max 4 per table)
- Link fields between tables use fieldtype "Link" with options = "HF <OtherTableName>"
- Select fields: options = newline-separated values, e.g. "active\ninactive\npending"
- nav: include 2-4 items — at least one per table, plus a chat item
- views: one entry per table

Do not install unless the user explicitly confirms. If install_huf_app succeeds, tell the user their app is live and they can find it at /apps.""",
    })
    doc.append("agent_tool", {"tool": "install_huf_app"})
    doc.insert(ignore_permissions=True)
```

---

### Frontend (TypeScript / React)

#### 6. `frontend/src/data/doctypes.ts` — MODIFY

Add the new DocType constant. Find the `doctype` object and add:

```typescript
// Existing pattern (add this line):
HufApp: "Huf App",
```

---

#### 7. `frontend/src/services/appApi.ts` — NEW

```typescript
import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export interface HufAppSummary {
  name: string;       // same as app_id
  app_id: string;
  label: string;
  description: string;
  icon: string;
  shell: 'chat' | 'dashboard' | 'list';
  agent: string;
  status: 'Active' | 'Disabled';
}

export interface HufAppManifest {
  app_id: string;
  label: string;
  description?: string;
  icon?: string;
  tables: Array<{
    table_name: string;
    description?: string;
    fields: Array<{
      fieldname: string;
      label: string;
      fieldtype: string;
      reqd?: number;
      in_list_view?: number;
      options?: string;
    }>;
  }>;
  agent: {
    agent_name: string;
    instructions: string;
    model?: string;
    provider?: string;
  };
  knowledge?: Array<{
    source_name: string;
    knowledge_type: string;
    inputs: Array<{ input_type: string; text?: string }>;
  }>;
  shell: 'chat' | 'dashboard' | 'list';
  nav: Array<{
    label: string;
    type?: 'collection' | 'chat';
    table?: string;
    view?: 'grid' | 'list' | 'table';
    filter?: Array<[string, string, string]>;
  }>;
  views: Array<{
    table: string;
    collection_layout: 'grid' | 'list' | 'table';
    card_variant: 'summary-first' | 'data-first';
    list_fields: string[];
    record_view: 'form' | 'view';
  }>;
}

export async function getHufApps(): Promise<HufAppSummary[]> {
  try {
    return await db.getDocList(doctype.HufApp, {
      fields: ['name', 'app_id', 'label', 'description', 'icon', 'shell', 'agent', 'status'],
      filters: [['status', '=', 'Active']],
      orderBy: { field: 'creation', order: 'desc' },
    }) as HufAppSummary[];
  } catch (e) {
    handleFrappeError(e, 'Failed to load apps');
    return [];
  }
}

export async function getHufApp(appId: string): Promise<HufAppManifest> {
  try {
    const result = await call.get('huf.ai.app_installer.get_huf_app', { app_id: appId });
    return result.message as HufAppManifest;
  } catch (e) {
    handleFrappeError(e, 'Failed to load app');
    throw e;
  }
}

export async function deleteHufApp(appId: string): Promise<void> {
  try {
    await call.delete('huf.ai.app_installer.delete_huf_app', { app_id: appId });
  } catch (e) {
    handleFrappeError(e, 'Failed to delete app');
    throw e;
  }
}
```

---

#### 8. `frontend/src/pages/AppRegistryPage.tsx` — NEW

Renders the list of installed Huf Apps as an ItemCard grid.

```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, ExternalLink } from 'lucide-react';
import PageLayout from '@/components/dashboard/layouts/PageLayout';
import GridView from '@/components/dashboard/views/GridView';
import ItemCard from '@/components/dashboard/cards/ItemCard';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { getHufApps, deleteHufApp, type HufAppSummary } from '@/services/appApi';

export default function AppRegistryPage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState<HufAppSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHufApps().then(setApps).finally(() => setLoading(false));
  }, []);

  async function handleDelete(appId: string) {
    if (!confirm(`Delete app "${appId}"? The data tables will remain.`)) return;
    try {
      await deleteHufApp(appId);
      setApps(prev => prev.filter(a => a.app_id !== appId));
      toast.success('App deleted');
    } catch {
      // handleFrappeError already toasts
    }
  }

  return (
    <PageLayout
      toolbar={
        <Button onClick={() => navigate('/apps/new')}>
          <Plus className="w-4 h-4 mr-2" /> New App
        </Button>
      }
    >
      <GridView
        items={apps}
        loading={loading}
        keyExtractor={a => a.app_id}
        columns={{ sm: 1, md: 2, lg: 3 }}
        emptyState={
          <div className="text-center py-16 text-muted-foreground">
            <p className="mb-4">No apps yet.</p>
            <Button onClick={() => navigate('/apps/new')}>Build your first app</Button>
          </div>
        }
        renderItem={app => (
          <ItemCard
            key={app.app_id}
            title={app.label}
            description={app.description}
            status={{ label: app.shell, variant: 'secondary' }}
            metadata={[{ label: 'Agent', value: app.agent }]}
            actions={[
              {
                icon: ExternalLink,
                label: 'Launch',
                onClick: () => navigate(`/apps/${app.app_id}`),
              },
            ]}
            menuActions={[
              {
                icon: Trash2,
                label: 'Delete',
                onClick: () => handleDelete(app.app_id),
                variant: 'destructive',
              },
            ]}
            onClick={() => navigate(`/apps/${app.app_id}`)}
          />
        )}
      />
    </PageLayout>
  );
}
```

---

#### 9. `frontend/src/pages/AppPlannerPage.tsx` — NEW

A thin wrapper around ChatWindowV2, pre-scoped to the "App Planner" agent. The entire app-building conversation happens here. When the agent calls `install_huf_app`, the app appears in the registry.

```tsx
import ChatWindow from '@/components/chat/ChatWindowV2';
import { useNavigate } from 'react-router-dom';

// The "App Planner" agent is created at install time (see huf/install.py).
// ChatWindowV2 with no chatId opens a new conversation and allows agent selection.
// We pass a default agentName so it starts scoped to the planner.
export default function AppPlannerPage() {
  const navigate = useNavigate();

  function handleConversationCreated(conversationId: string) {
    navigate(`/apps/new/${conversationId}`, { replace: true });
  }

  return (
    <div className="h-full">
      <ChatWindow
        chatId={null}
        defaultAgentName="App Planner"
        onConversationCreated={handleConversationCreated}
      />
    </div>
  );
}
```

**Note:** `defaultAgentName` is a new prop on ChatWindowV2 (see ChatWindowV2 modification below).

---

#### 10. `frontend/src/pages/AppLaunchPage.tsx` — NEW

Reads the manifest for a given app and renders the correct shell.

- Shell `"chat"` → renders `ChatWindowV2` scoped to the app's agent (new conversation each session or pick existing)
- Shell `"dashboard"` → renders `PageLayout` + `FilterBar` + first view's collection as primary content + nav tabs
- Shell `"list"` → renders `PageLayout` + `FilterBar` + `DataRecordList` for the primary table

```tsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getHufApp, type HufAppManifest } from '@/services/appApi';
import AppDashboardShell from '@/components/apps/AppDashboardShell';
import AppListShell from '@/components/apps/AppListShell';
import ChatWindow from '@/components/chat/ChatWindowV2';
import { Loader2 } from 'lucide-react';

export default function AppLaunchPage() {
  const { appId } = useParams<{ appId: string }>();
  const [manifest, setManifest] = useState<HufAppManifest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (appId) getHufApp(appId).then(setManifest).finally(() => setLoading(false));
  }, [appId]);

  if (loading) return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin" /></div>;
  if (!manifest) return <div className="p-8 text-muted-foreground">App not found.</div>;

  if (manifest.shell === 'chat') {
    return (
      <div className="h-full">
        <ChatWindow chatId={null} defaultAgentName={manifest.agent.agent_name} />
      </div>
    );
  }
  if (manifest.shell === 'dashboard') return <AppDashboardShell manifest={manifest} />;
  if (manifest.shell === 'list') return <AppListShell manifest={manifest} />;
  return null;
}
```

---

#### 11. `frontend/src/components/apps/AppDashboardShell.tsx` — NEW

Renders the dashboard shell: tabs for each nav item, primary collection view using existing components.

```tsx
import { useState } from 'react';
import { type HufAppManifest } from '@/services/appApi';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import AppCollectionView from './AppCollectionView';
import ChatWindow from '@/components/chat/ChatWindowV2';

interface Props { manifest: HufAppManifest }

export default function AppDashboardShell({ manifest }: Props) {
  const [activeTab, setActiveTab] = useState(manifest.nav[0]?.label ?? '');

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <h1 className="text-xl font-semibold">{manifest.label}</h1>
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
        <TabsList>
          {manifest.nav.map(item => (
            <TabsTrigger key={item.label} value={item.label}>{item.label}</TabsTrigger>
          ))}
        </TabsList>
        {manifest.nav.map(item => (
          <TabsContent key={item.label} value={item.label} className="flex-1">
            {item.type === 'chat' ? (
              <ChatWindow chatId={null} defaultAgentName={manifest.agent.agent_name} />
            ) : (
              <AppCollectionView
                manifest={manifest}
                tableName={item.table!}
                layoutOverride={item.view}
                filterOverride={item.filter}
              />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
```

---

#### 12. `frontend/src/components/apps/AppListShell.tsx` — NEW

Simple shell for list-first apps. Primary table displayed with FilterBar + DataRecordList.

```tsx
import { type HufAppManifest } from '@/services/appApi';
import AppCollectionView from './AppCollectionView';

interface Props { manifest: HufAppManifest }

export default function AppListShell({ manifest }: Props) {
  const primaryView = manifest.views[0];
  if (!primaryView) return null;
  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <h1 className="text-xl font-semibold">{manifest.label}</h1>
      <AppCollectionView manifest={manifest} tableName={primaryView.table} />
    </div>
  );
}
```

---

#### 13. `frontend/src/components/apps/AppCollectionView.tsx` — NEW

Core reusable component. Given a manifest + table name, fetches records and renders the correct layout using existing Huf components. No new rendering logic — pure composition.

```tsx
import { useEffect, useState } from 'react';
import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { type HufAppManifest } from '@/services/appApi';
import GridView from '@/components/dashboard/views/GridView';
import ItemCard from '@/components/dashboard/cards/ItemCard';
import DataRecordList from '@/components/data-table/DataRecordList';
import FilterBar from '@/components/dashboard/filters/FilterBar';
import { useDebounce } from '@/hooks/useDebounce';

interface Props {
  manifest: HufAppManifest;
  tableName: string;
  layoutOverride?: 'grid' | 'list' | 'table';
  filterOverride?: Array<[string, string, string]>;
}

export default function AppCollectionView({ manifest, tableName, layoutOverride, filterOverride }: Props) {
  const viewConfig = manifest.views.find(v => v.table === tableName);
  const layout = layoutOverride ?? viewConfig?.collection_layout ?? 'list';
  const listFields = viewConfig?.list_fields ?? [];

  // Derive the DocType name: HUF tables are named "HF <TableName>"
  const doctypeName = `HF ${tableName}`;

  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const debouncedSearch = useDebounce(search, 300);

  useEffect(() => {
    setLoading(true);
    const filters: Array<[string, string, string]> = [...(filterOverride ?? [])];
    if (debouncedSearch) {
      // Search on first list field if it's a Data type
      const firstField = listFields[0];
      if (firstField) filters.push([firstField, 'like', `%${debouncedSearch}%`]);
    }
    db.getDocList(doctypeName, {
      fields: ['name', ...listFields],
      filters: filters as never,
      limit: 50,
    })
      .then(setRecords)
      .catch(e => handleFrappeError(e, `Failed to load ${tableName}`))
      .finally(() => setLoading(false));
  }, [doctypeName, debouncedSearch, JSON.stringify(filterOverride)]);

  // Field definitions for DataRecordList
  const fieldDefs = listFields.map(f => {
    const fieldDef = manifest.tables
      .find(t => t.table_name === tableName)
      ?.fields.find(fd => fd.fieldname === f);
    return {
      fieldname: f,
      label: fieldDef?.label ?? f,
      fieldtype: (fieldDef?.fieldtype ?? 'Data') as never,
      in_list_view: 1 as const,
    };
  });

  return (
    <div className="flex flex-col gap-4 h-full">
      <FilterBar
        searchPlaceholder={`Search ${tableName}...`}
        searchValue={search}
        onSearchChange={setSearch}
      />
      {layout === 'grid' ? (
        <GridView
          items={records}
          loading={loading}
          keyExtractor={r => String(r.name)}
          columns={{ sm: 1, md: 2, lg: 3 }}
          renderItem={r => (
            <ItemCard
              title={String(r[listFields[0]] ?? r.name ?? '')}
              description={listFields[1] ? String(r[listFields[1]] ?? '') : undefined}
              metadata={listFields.slice(2).map(f => ({
                label: fieldDefs.find(fd => fd.fieldname === f)?.label ?? f,
                value: String(r[f] ?? ''),
              }))}
            />
          )}
        />
      ) : (
        <DataRecordList records={records} fields={fieldDefs} loading={loading} />
      )}
    </div>
  );
}
```

---

#### 14. `frontend/src/components/chat/ChatWindowV2.tsx` — MODIFY

Add one optional prop `defaultAgentName?: string` to the existing `ChatWindowProps` interface. When provided and `chatId` is null (new conversation), pre-select that agent.

**Find** the existing `ChatWindowProps` interface (exact location: `frontend/src/components/chat/ChatWindowV2.tsx`):
```typescript
interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    sidebarOpen?: boolean;
    onToggleSidebar?: () => void;
}
```

**Replace with:**
```typescript
interface ChatWindowProps {
    chatId?: string | null;
    onConversationCreated?: (conversationId: string, agentName?: string) => void;
    sidebarOpen?: boolean;
    onToggleSidebar?: () => void;
    defaultAgentName?: string;   // Pre-select this agent for new conversations
}
```

Then inside the component, find where the agent is selected for a new conversation and apply `defaultAgentName` as the initial value. The exact implementation depends on how agent selection state is managed in the component — find the agent state initializer and set it to `defaultAgentName ?? ''`.

---

#### 15. `frontend/src/App.tsx` — MODIFY

Add four new lazy imports and four routes. Find the existing lazy imports block and add:

```typescript
const AppRegistryPage = lazy(() => import('./pages/AppRegistryPage'));
const AppPlannerPage = lazy(() => import('./pages/AppPlannerPage'));
const AppLaunchPage = lazy(() => import('./pages/AppLaunchPage'));
```

Find the `<Routes>` block and add (after the `/data` routes):

```tsx
<Route
  path="/apps"
  element={
    <ProtectedRoute>
      <UnifiedLayout headerActions={null}>
        <Suspense fallback={<PageLoader />}>
          <AppRegistryPage />
        </Suspense>
      </UnifiedLayout>
    </ProtectedRoute>
  }
/>
<Route
  path="/apps/new"
  element={
    <ProtectedRoute>
      <UnifiedLayout hideHeader>
        <Suspense fallback={<PageLoader />}>
          <AppPlannerPage />
        </Suspense>
      </UnifiedLayout>
    </ProtectedRoute>
  }
/>
<Route
  path="/apps/new/:chatId"
  element={
    <ProtectedRoute>
      <UnifiedLayout hideHeader>
        <Suspense fallback={<PageLoader />}>
          <AppPlannerPage />
        </Suspense>
      </UnifiedLayout>
    </ProtectedRoute>
  }
/>
<Route
  path="/apps/:appId"
  element={
    <ProtectedRoute>
      <UnifiedLayout hideHeader>
        <Suspense fallback={<PageLoader />}>
          <AppLaunchPage />
        </Suspense>
      </UnifiedLayout>
    </ProtectedRoute>
  }
/>
```

---

#### 16. `frontend/src/components/app-sidebar.tsx` — MODIFY

Add "Apps" to the `allNavItems` array. Find the `allNavItems` array and insert:

```typescript
{
  title: "Apps",
  url: "/apps",
  icon: LayoutGrid,    // already imported from lucide-react; if not, add to import
  capability: null,    // visible to all logged-in users
},
```

Insert it after the Dashboard entry so it appears second in the sidebar.

If `LayoutGrid` is not already imported from `lucide-react`, add it to the existing import:
```typescript
import { ..., LayoutGrid } from 'lucide-react';
```

---

## Expected Output

After these changes are applied and the backend is migrated (`bench migrate`):

1. **Sidebar** shows "Apps" as the second nav item, visible to all users.
2. **`/apps`** shows a grid of installed Huf Apps (empty initially, with "Build your first app" CTA).
3. **`/apps/new`** opens a chat interface with the App Planner agent.
4. User describes their need → agent proposes schema → user iterates → user confirms → agent calls `install_huf_app` → toast confirms success → agent says "Your app is live at /apps/student-counselor".
5. **`/apps/student-counselor`** opens the app in its shell (dashboard/list/chat).
   - Dashboard shell: tabs across the top for each nav item. Active tab shows the collection (grid or list of records).
   - List shell: FilterBar + DataRecordList for the primary table.
   - Chat shell: ChatWindowV2 scoped to the app's agent.
6. Native search works via FilterBar's text input on any collection view.
7. FTS/vector search works via the agent in chat views — user asks "find students at risk" → agent uses CRUD tools + knowledge tools.
8. Deleting an app from the registry removes the Agent and Huf App record; HUF tables and their data are preserved.

---

## Not In Scope (Phase 1)

- Calendar, Kanban, Timeline collection layouts
- SearchShell (dedicated search-first UI)
- Image-first card variant
- Record detail + chat sidebar combo view
- Data-derived vector search (embedding table records)
- App editing / manifest updates post-install
- Multi-user app permissions
