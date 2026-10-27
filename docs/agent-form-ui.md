# Agent Form UI — Layout, Fields & Relationships

> Visual reference for the Agent create/edit form (`/agents/:id`) and all connected modals/forms.

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  BREADCRUMB: Agents > [Agent Name]                                  │
├─────────────────────────────────────────────────────────────────────┤
│  AGENT HEADER                                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  [Editable Agent Name input]  [Active/Disabled] [Provider]   │  │
│  │                               [Model]                         │  │
│  │  ⏱ N active triggers                                          │  │
│  │  Last run: X ago   Total runs: N                              │  │
│  │                                          [▶] [Chat] [Save] [⋮]│  │
│  └───────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  TAB BAR                                                             │
│  [ General ] [ Behavior ] [ Triggers ] [ Tools ] [ Knowledge ]      │
│  [ Permissions ] [ Advanced ]                                        │
├─────────────────────────────────────────────────────────────────────┤
│  TAB CONTENT (scrollable)                                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent Header

| Element | Type | Notes |
|---------|------|-------|
| Agent Name | Inline input (text) | Editable directly, updates form |
| Active / Disabled badge | Badge | Reflects `disabled` field |
| Provider badge | Badge (outline) | Shows resolved provider display name |
| Model badge | Badge (outline) | Shows resolved model display name |
| Active triggers count | Info row | Shows clock icon + count if > 0 |
| Last run / Total runs | Info row | Hidden for new agents |
| **▶ Run Test** button | Icon button | Runs a test execution; hidden for new agents |
| **Chat** button | Outline button | Opens chat pre-filtered to this agent; hidden if `allow_chat` is off or agent is new |
| **Create / Save** button | Primary button | Label: "Create" (new) / "Save" (existing); only shown when form is dirty or related data changed |
| **⋮ More** dropdown | Dropdown menu | Contains: Disable toggle (Switch), View Logs (existing agents only) |

> Note: Duplicate and Delete are implemented in code but currently commented out.

---

## Tab 1 — General

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: LLM Configuration                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Agent Name [text input]           ← required             │   │
│  │ ▶ Description  (collapsible accordion)                   │   │
│  │   [textarea]                                             │   │
│  │                                                          │   │
│  │ Provider [dropdown]   Model [dropdown]                   │   │
│  │ Temperature [slider 0–2]   Top P [slider 0–1]            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Card: Prompt Source                                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Prompt Mode [dropdown: Local | Template]                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  IF Prompt Mode = "Local":                                       │
│  Card: Instructions                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ [textarea — system prompt]  [⛶ Expand]  [✨ Optimize]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  IF Prompt Mode = "Template":                                    │
│  Card: Prompt Template                                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Agent Prompt [combobox → Agent Prompt doctype]           │   │
│  │ Lock Template Version [switch]                           │   │
│  │ Attached at Version [read-only]                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Card: Prompt Caching                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Enable Prompt Caching [switch]                           │   │
│  │  IF enabled:                                             │   │
│  │    Cache Control Type [dropdown: auto | ephemeral]       │   │
│  │    Cache System Message [switch]                         │   │
│  │    Cache Conversation History [switch]                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Field Reference — General Tab

| Field | Type | Default | Help Text |
|-------|------|---------|-----------|
| Agent Name | Text input | — | "Unique agent name" |
| Description | Textarea (accordion) | — | "A brief description of the agent's purpose" |
| Provider | Select | — | Clears model when changed |
| Model | Select | — | "Filtered by selected provider"; disabled until provider selected |
| Temperature | Slider (0–2, step 0.1) | 1 | "Lower = focused, higher = creative" |
| Top P | Slider (0–1, step 0.05) | 1 | "Nucleus sampling parameter" |
| Prompt Mode | Select (Local/Template) | Local | "Local stores instructions directly; Template links to a reusable Agent Prompt" |
| Instructions | Textarea | — | Only when Prompt Mode = Local |
| Agent Prompt | Combobox | — | Only when Prompt Mode = Template; required in that mode |
| Lock Template Version | Switch | false | "Keep agent pinned to attached version" |
| Attached at Version | Read-only | — | Shows recorded version or pending notice |
| Enable Prompt Caching | Switch | false | Supported: OpenAI, Anthropic, Bedrock, Deepseek |
| Cache Control Type | Select (auto/ephemeral) | — | Shown only when caching enabled |
| Cache System Message | Switch | false | Shown only when caching enabled |
| Cache Conversation History | Switch | false | Shown only when caching enabled |

---

## Tab 2 — Behavior

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: Conversation Settings                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Allow Chat           [switch]  (disabled if multi-run)   │   │
│  │ Persist History      [switch]                            │   │
│  │ Persist per User     [switch]                            │   │
│  │ Enable Multi Run     [switch]  (disables chat)           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  IF Enable Multi Run = on:                                       │
│  Card: Default Plan                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ┌────┬────────────┬─────────────────┬────────┬────────┐ │   │
│  │ │ #  │ Status     │ Instruction     │ Output │        │ │   │
│  │ ├────┼────────────┼─────────────────┼────────┼────────┤ │   │
│  │ │ 1  │ [dropdown] │ [textarea]      │ [text] │ [🗑]   │ │   │
│  │ └────┴────────────┴─────────────────┴────────┴────────┘ │   │
│  │                               [ + Add Row ]              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Field Reference — Behavior Tab

| Field | Type | Notes |
|-------|------|-------|
| Allow Chat | Switch | Requires Persist History to be on; disabled when Multi Run is active |
| Persist History | Switch | Turning off also disables Allow Chat |
| Persist per User (Doc/Schedule) | Switch | Creates per-user history for automation runs |
| Enable Multi Run | Switch | Disables Allow Chat when turned on |
| Default Plan rows | Table (dynamic) | Only visible when Multi Run is on |
| — Step # | Auto-numbered | Read-only |
| — Status | Select (pending/in_progress/done/failed) | Default: pending |
| — Instruction | Textarea | What this step should do |
| — Output | Text | Reference for output storage |

---

## Tab 3 — Triggers

```
┌─────────────────────────────────────────────────────────────────┐
│  Section: Agent Triggers                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Filter by Type [dropdown]  Filter by Status [dropdown]  │   │
│  │ Showing N triggers                  [ + Add Trigger ]   │   │
│  │                                                          │   │
│  │ IF no triggers:                                          │   │
│  │   Empty state → [ + Add Trigger ]                        │   │
│  │                                                          │   │
│  │ IF triggers exist:                                       │   │
│  │ ┌──────────┬──────────┬────────┬───────────┬─────────┐  │   │
│  │ │ Type     │ Details  │ Status │ Last Run  │ Actions │  │   │
│  │ ├──────────┼──────────┼────────┼───────────┼─────────┤  │   │
│  │ │ Schedule │ …        │ Active │ 2h ago    │ ✎  🗑   │  │   │
│  │ └──────────┴──────────┴────────┴───────────┴─────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Add/Edit Trigger → opens TriggerModal** (see Modals section)

---

## Tab 4 — Tools

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: Tools  (Server icon)                    [ + Add Tool ]    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2-column grid of tool cards:                            │   │
│  │  ┌────────────────────────┐  ┌────────────────────────┐ │   │
│  │  │ [icon] Tool Name       │  │ [icon] Tool Name       │ │   │
│  │  │ Description (2 lines) │  │ Description (2 lines) │ │   │
│  │  │ ⚠ Used in N agents    │  │                        │ │   │
│  │  │          (hover) ✎ 🗑 │  │          (hover) ✎ 🗑 │ │   │
│  │  └────────────────────────┘  └────────────────────────┘ │   │
│  │                                                          │   │
│  │  Empty state: "No tools configured yet"                  │   │
│  │               [ + Add Tool ]                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Card: Model Context Protocol (MCP)  (Plug icon)                 │
│                                              [ + Connect MCP ]   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  List of connected MCP servers:                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │ [Server Name] [connected] [N tools]              │   │   │
│  │  │ Description                                      │   │   │
│  │  │ https://server-url        [⟳] [toggle] [🗑]     │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                                                          │   │
│  │  Empty state: "No MCP servers connected"                 │   │
│  │               [ + Connect MCP Server ]                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**MCP server status badge logic:**

| Condition | Badge |
|-----------|-------|
| MCP server itself disabled | `server disabled` (secondary) |
| MCP server OK but agent disabled it | `disabled` (secondary) |
| Both enabled | `connected` (default) |

---

## Tab 5 — Knowledge

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: Knowledge Sources  (BookOpen icon)   [ + Add Knowledge ]  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  2-column grid:                                          │   │
│  │  ┌────────────────────────────┐                         │   │
│  │  │ [📖] Source Name           │                         │   │
│  │  │      [MANDATORY] [P: 1]    │                         │   │
│  │  │ Description (2 lines)      │                         │   │
│  │  │ Max chunks: 5  Budget: 500 │                         │   │
│  │  │            (hover) ✎ 🗑   │                         │   │
│  │  └────────────────────────────┘                         │   │
│  │                                                          │   │
│  │  Empty state: "No knowledge sources linked yet"          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tab 6 — Permissions

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: Access Control                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Allow Guest API Access  [switch]                         │   │
│  │                                                          │   │
│  │ Allowed Users  [multi-select combobox]                   │   │
│  │ Allowed Roles  [multi-select combobox]                   │   │
│  │                                                          │   │
│  │  IF users/roles selected:                                │   │
│  │  ℹ "X users and Y roles have access"                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

| Field | Type | Notes |
|-------|------|-------|
| Allow Guest API Access | Switch | Default: false |
| Allowed Users | Multi-select combobox | Searches User doctype |
| Allowed Roles | Multi-select combobox | Excludes Guest role |

---

## Tab 7 — Advanced

```
┌─────────────────────────────────────────────────────────────────┐
│  Card: Context Settings                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Context Strategy [select: None | Summarize | FIFO]       │   │
│  │ Summary Ratio    [number input]  (default: 0.7)          │   │
│  │ IF strategy = Summarize:                                  │   │
│  │   Summary Model  [select — all models]                   │   │
│  │ History Limit    [number input]  (placeholder: 50)       │   │
│  │ Max Knowledge Tokens [number input] (placeholder: 2000)  │   │
│  │ Max Turns        [number input]  (placeholder: 10)       │   │
│  │ Allow Conversation Data Management  [switch]             │   │
│  │ Autonaming of Conversation Title    [switch]             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Card: Huf UI                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Agent Color  [text input #rrggbb]  [color picker]        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Card: Model Modality Settings                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Image Generation Model  [select — image-capable models]  │   │
│  │ TTS Model               [select — TTS-capable models]    │   │
│  │ TTS Voice               [text input]                     │   │
│  │ STT Model               [select — STT-capable models]    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

| Field | Type | Default | Help Text |
|-------|------|---------|-----------|
| Context Strategy | Select | None | "None" / "Summarize" compresses old messages / "FIFO" drops them |
| Summary Ratio | Number | 0.7 | Fraction of oldest messages to summarize |
| Summary Model | Select | — | Only shown when strategy = Summarize; defaults to agent's own model |
| History Limit | Number | 50 | Max messages before strategy applies |
| Max Knowledge Tokens | Number | 2000 | Token cap for injected knowledge |
| Max Turns | Number | 10 | Max consecutive agent steps per run |
| Allow Conversation Data Mgmt | Switch | false | Lets agent store key-value pairs in conversation |
| Autonaming of Conversation Title | Switch | false | Auto-update chat title from initial context |
| Agent Color | Text + color picker | — | Hex `#rrggbb`; used as avatar background in chat |
| Image Generation Model | Select | — | Filtered to models with `image` modality |
| TTS Model | Select | — | Filtered to models with `tts` modality |
| TTS Voice | Text | — | Provider-specific voice name |
| STT Model | Select | — | Filtered to models with `stt` modality |

---

## Modals

### TriggerModal

Opened by: Triggers tab → Add Trigger / Edit (pencil icon)

```
┌──────────────────────────────────────────────────┐
│  Add / Edit Trigger                               │
│  ─────────────────────────────────────────────── │
│  Trigger Name  [text input]   (new only)          │
│  Trigger Type  [select]       (required)          │
│  Active        [switch]       (default: on)       │
│                                                   │
│  ── Dynamic fields by type ──                     │
│                                                   │
│  Schedule:                                        │
│    Scheduled Interval  [select]                   │
│    Interval Count      [number]                   │
│                                                   │
│  Doc Event:                                       │
│    Reference DocType   [select]                   │
│    Doc Event           [select]                   │
│    Condition           [text/expression]          │
│                                                   │
│  Webhook:                                         │
│    Webhook Slug        [text]                     │
│    Webhook Key         [text]                     │
│                                                   │
│  App Event:                                       │
│    App Name            [text]                     │
│    Event Name          [text]                     │
│                                                   │
│  Manual: (no extra fields)                        │
│                                                   │
│                       [ Cancel ]  [ Save ]        │
└──────────────────────────────────────────────────┘
```

---

### SelectToolsModal

Opened by: Tools tab → Add Tool

```
┌──────────────────────────────────────────────────┐
│  Add Tools                                        │
│  ─────────────────────────────────────────────── │
│  Tabs: [ Tool Library ]  [ Create New ]           │
│                                                   │
│  Tool Library tab:                                │
│    [🔍 Search by name/description]                │
│    Tool Type [dropdown filter]                    │
│                                                   │
│    Grid of tool cards:                            │
│    ┌──────────────────────┐                       │
│    │ ☑ [icon] Tool Name   │                       │
│    │   Description        │                       │
│    │   [Type] [N agents]  │                       │
│    └──────────────────────┘                       │
│                                                   │
│  Create New tab:                                  │
│    Template grid → select template                │
│    → ToolCreationForm                             │
│                                                   │
│                       [ Cancel ]  [ Add Tools ]   │
└──────────────────────────────────────────────────┘
```

---

### ToolFormModal

Opened by: Tools tab → Edit tool (pencil icon), or from SelectToolsModal → Create New

```
┌──────────────────────────────────────────────────┐
│  Create / Edit Tool                               │
│  ─────────────────────────────────────────────── │
│  Tool Name        [text]    (required)            │
│  Tool Type        [select]                        │
│  Description      [textarea]                      │
│                                                   │
│  ── Type-specific fields ──                       │
│  Reference DocType | Agent | Function Path        │
│  Function Name | Pass Params as JSON [switch]     │
│  Provider App | Base URL                          │
│  Required Permission | Read-only [switch]         │
│  Allowed for Guest [switch]                       │
│                                                   │
│  Parameters       [dynamic table]                 │
│  HTTP Headers     [dynamic table]                 │
│                                                   │
│              [ Cancel ]  [ Back ]  [ Save ]       │
└──────────────────────────────────────────────────┘
```

---

### SelectMCPServersModal

Opened by: Tools tab → Connect MCP

```
┌──────────────────────────────────────────────────┐
│  Connect MCP Servers                              │
│  ─────────────────────────────────────────────── │
│  [🔍 Search by name/description]                  │
│                                                   │
│  MCP Server cards:                                │
│  ┌────────────────────────────────────┐           │
│  │ ☑  Server Name  [Status]           │           │
│  │    Description                     │           │
│  │    https://server-url              │           │
│  │    [N tools]                       │           │
│  └────────────────────────────────────┘           │
│                                                   │
│                  [ Cancel ]  [ Add Servers ]       │
└──────────────────────────────────────────────────┘
```

---

### AgentKnowledgeModal

Opened by: Knowledge tab → Add Knowledge / Edit (pencil icon)

```
┌──────────────────────────────────────────────────┐
│  Link Knowledge Source                            │
│  ─────────────────────────────────────────────── │
│  Knowledge Source  [combobox]  (required)         │
│  Mode              [select: Mandatory | Optional] │
│  Priority          [number]                       │
│  Max Chunks        [number]                       │
│  Token Budget      [number]                       │
│  Description       [text]    (optional)           │
│                                                   │
│                       [ Cancel ]  [ Save ]        │
└──────────────────────────────────────────────────┘
```

---

## Entity Relationship Diagram

```
                            ┌─────────────────────┐
                            │       AGENT          │
                            │  (Agent DocType)      │
                            └──────────┬───────────┘
                                       │
           ┌───────────────────────────┼──────────────────────────┐
           │                           │                          │
    one Provider                 one Model                  many Triggers
           │                           │                          │
    ┌──────▼──────┐            ┌───────▼──────┐         ┌────────▼────────┐
    │ AI Provider  │            │   AI Model   │         │  Agent Trigger   │
    │ (credentials)│            │(model config)│         │ Types:           │
    └─────────────┘            └─────────────┘         │ - Schedule       │
                                                        │ - Doc Event      │
           ┌───────────────────────────┬               │ - Webhook         │
           │                           │               │ - App Event       │
    many Tools                  many MCP Servers       │ - Manual          │
           │                           │               └─────────────────┘
    ┌──────▼────────────┐     ┌────────▼──────────┐
    │ Agent Tool        │     │  MCP Server        │
    │ Function          │     │  (external server) │
    │ Types:            │     │  - server_url       │
    │ - CRUD (read/     │     │  - tool_count       │
    │   write/delete)   │     │  - enabled toggle   │
    │ - Custom function │     │  Links to:          │
    │ - HTTP request    │     │  MCP Server DocType │
    │ - Agent           │     └────────────────────┘
    │ - Run Flow        │
    └───────────────────┘
           │
    many Agents can share same tool
    (shown as amber "Used in N agents" badge)

           ┌─────────────────┐
           │ Knowledge Source │  ◄── linked via AgentKnowledgeModal
           │ (RAG/FTS5)       │
           │ - mode           │
           │ - priority       │
           │ - max_chunks     │
           │ - token_budget   │
           └─────────────────┘

    IF Prompt Mode = Template:
           ┌─────────────────┐
           │  Agent Prompt   │  ◄── selected via combobox in General tab
           │  (library item) │
           │  - version      │
           │  - lock support │
           └─────────────────┘
```

---

## Form State & Save Logic

```
AgentFormPage state:
│
├── form (React Hook Form + Zod)
│     └── AgentFormValues (all scalar fields)
│
├── selectedTools[]        ← compared to initialTools to detect changes
├── mcpServers[]           ← compared to initialMCPServers to detect changes
├── knowledgeSources[]     ← compared to initialKnowledge to detect changes
│
└── showSaveButton = form.isDirty
                  OR selectedTools ≠ initialTools
                  OR mcpServers ≠ initialMCPServers
                  OR knowledgeSources ≠ initialKnowledge
```

**On Save / Create:**
1. Validate form with Zod schema (tab-aware: errors map to tab names for UX)
2. Build `AgentUpdatePayload` merging form values + tool refs + mcp refs + knowledge refs
3. Call `createAgent` (new) or `updateAgent` (existing) via `agentApi`
4. Toast success/error; navigate to `/agents/:newId` after create

---

## Navigation & Cross-Links

| From | Action | Destination |
|------|--------|-------------|
| Agent form header | Chat button | `/chat?agent=<id>` |
| Agent form header | ▶ Run Test | `/executions/:runId` |
| Agent form header ⋮ | View Logs | `/executions?agent=<id>` |
| Tools tab — MCP server name | Click link | `/mcp/:mcpId` |
| Breadcrumb | Agents link | `/agents` |

---

## Component File Map

```
frontend/src/
├── pages/
│   ├── AgentFormPageWrapper.tsx   ← UnifiedLayout + breadcrumbs wrapper
│   └── AgentFormPage.tsx          ← Main form logic, state, API calls
│
└── components/agent/
    ├── types.ts                   ← Zod schema + AgentFormValues type
    ├── AgentHeader.tsx            ← Top action bar
    ├── GeneralTab.tsx             ← LLM config, prompt, caching
    ├── BehaviorTab.tsx            ← Conversation + multi-run plan
    ├── TriggersTab.tsx            ← Trigger list + filters
    ├── ToolsTab.tsx               ← Tools grid + MCP servers
    ├── KnowledgeTab.tsx           ← Knowledge sources grid
    ├── PermissionsTab.tsx         ← Users/roles access control
    ├── AdvancedTab.tsx            ← Context, UI color, modalities
    ├── TriggerModal.tsx           ← Add/edit trigger dialog
    ├── AgentKnowledgeModal.tsx    ← Link knowledge source dialog
    ├── InstructionsTextarea.tsx   ← Instructions with expand/optimize
    ├── PromptTemplateSection.tsx  ← Template mode combobox + version
    └── DefaultPlanTable.tsx       ← Multi-run plan editable table

└── components/tools/
    ├── SelectToolsModal.tsx       ← Tool library + create new tabs
    ├── SelectMCPServersModal.tsx  ← MCP server selection dialog
    ├── ToolFormModal.tsx          ← Tool create/edit form
    ├── ToolCreationForm.tsx       ← Type-specific tool fields
    └── toolIconMap.ts             ← Icon per tool type
```
