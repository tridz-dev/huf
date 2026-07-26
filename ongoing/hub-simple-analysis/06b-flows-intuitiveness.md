# Core Product Flows Intuitiveness Audit

**Scope:** Static, read-only audit of the HUF frontend core product flows for two personas:  
- **P1** = normal business user (non-technical)  
- **P2** = functional consultant / ERP-savvy, no code  

**Branch:** `feat/design-simplified-hub-homepage-interface` @ `4a28794d`  
**Method:** Code inspection only. No runtime testing, no file modifications.

---

## W1. IA / Navigation

### Sidebar nav as a business user sees it

File: `frontend/src/components/app-sidebar.tsx:33-159`

| Section | Order | Label | Icon |
|---------|-------|-------|------|
| (top) | 1 | Dashboard | Home |
| Build | 2 | Agents | Bot |
| Build | 3 | Agent Prompts | ScrollText |
| Build | 4 | Flows | Workflow |
| Build | 5 | Data | Database |
| Build | 6 | Knowledge | BookOpen |
| Operate | 7 | Chat | MessageSquare |
| Operate | 8 | Executions | Zap |
| Operate | 9 | Artifacts | Boxes |
| People | 10 | Users | Users |
| Settings (collapsible) | 11 | AI Providers | Plug |
| Settings | 12 | Models | Cpu |
| Settings | 13 | Agent Summary Prompts | ScrollText |
| Settings | 14 | Console | Terminal |
| Settings | 15 | Integrations | Link2 |
| Settings | 16 | Integration Services | Boxes |
| Settings | 17 | MCP Servers | Server |
| Settings | 18 | Roles | Shield |

### Hub slash commands

File: `frontend/src/components/hub/SlashCommandMenu.tsx:12-20`

Labels as shown in the palette:

| Command | Label | Description |
|---------|-------|-------------|
| `/flow` | Flow | Create, edit, or manage workflows |
| `/agent` | Agent | Create, configure, or run agents |
| `/users` | Users | Manage users and permissions |
| `/runs` | Executions | View and manage agent runs |
| `/cost` | Cost | View costs and optimize spending |
| `/knowledge` | Knowledge | Index and search knowledge sources |
| `/settings` | Settings | Configure providers and preferences |

### Hub mini-sidebar icons

File: `frontend/src/pages/HubSimplePage.tsx:50-57`

Labels: Home, Agents, Flows, Executions, Knowledge, AI Providers.

### Routes

File: `frontend/src/App.tsx:80-481`

Relevant route paths: `/`, `/dashboard`, `/agents`, `/agents/:id`, `/prompts`, `/summary-prompts`, `/flows`, `/flows/:flowId`, `/chat`, `/chat/:chatId`, `/executions`, `/executions/:runId`, `/artifacts`, `/knowledge`, `/data`, `/console`, `/mcp`, `/integrations`, `/integration-services`, `/providers`, `/models`, `/users`, `/roles`, `/settings`.

### Developer-framed labels

- **MCP Servers** (`app-sidebar.tsx:148`) — acronym only; P1/P2 will not know what MCP means.
- **Executions** (`app-sidebar.tsx:83`, `HubSimplePage.tsx:54`) — sounds like a technical/run-log term; the icon is `Zap` (lightning), not a clock/log.
- **Console** (`app-sidebar.tsx:130`) — a testing/debug surface, labeled like a developer tool.
- **Data** (`app-sidebar.tsx:62`) — actually builds dynamic DocTypes; the label is plain but the page is schema-builder territory.
- **Agent Prompts** / **Agent Summary Prompts** (`app-sidebar.tsx:50`, `app-sidebar.tsx:124`) — template-library concepts; P2 may guess, P1 likely won't.
- **Models** (`app-sidebar.tsx:118`) — ambiguous out of context (AI model vs data model).

### Mental model check: “make the AI answer invoice questions”

There is a coherent **high-level** model (Build → Operate), but the labels and grouping do not consistently reinforce it:

- A P1 who wants an AI to answer invoice questions would most naturally go to **Chat** (if an agent exists) or **Agents** (to make one).
- **Knowledge** is the right place to upload invoice policy docs, but only a builder sees it; operators cannot (`agent.use` capability required).
- **Flows** is for automation, not Q&A, so P1 may confuse it with "making the AI do something."
- **Data** lets users create custom tables (`HF ...` DocTypes); it is under Build but its label and icon make it look like the master data area, not a schema-design tool.
- **Executions** is under Operate, but its name and lightning icon do not clearly mean "history of AI runs."

> Verdict for W1: the structure exists, but several labels leak backend/dev vocabulary and the grouping does not make the "chat-first" job obvious to P1.

---

## W2. Agent Creation Flow

Entry: `/agents/new` → `frontend/src/pages/AgentFormPage.tsx`.

Tabs (file: `AgentFormPage.tsx:140-209`):

| Tab | Internal ID | Form fields / concerns |
|-----|-------------|------------------------|
| General | `general` | agent_name, provider, model, temperature, top_p, description, instructions, prompt_mode, agent_prompt, prompt_version_locked, enable_prompt_caching + cache sub-fields |
| Behavior | `behavior` | allow_chat, persist_conversation, persist_user_history, enable_multi_run, default_plan |
| Triggers | `triggers` | child-table-style list, no form fields here |
| Tools & MCP | `tools` | selectedTools, mcpServers |
| Knowledge | `knowledge` | knowledgeSources |
| Permissions | `permissions` | allow_guest, allowed_users, allowed_roles |
| Advanced Settings | `advanced` | context_strategy, summary_model, summary_ratio, summary_prompt_mode/template/prompt, history_limit, max_knowledge_tokens, max_turns, max_context_chars, enable_conversation_data, inject_conversation_data, conversation_data_api_permission, autonaming_of_conversation_title, agent_color, show_tool_execution_details, image_generation_model, tts_model, tts_voice, stt_model, allow_file_upload, enable_ocr, max_upload_size_mb |

### Required fields

From the form schema (`frontend/src/components/agent/types.ts:4-8`):

```ts
agent_name: z.string().min(1, 'Agent name is required'),
provider: z.string().min(1, 'Provider is required'),
model: z.string().min(1, 'Model is required'),
temperature: z.number().min(0).max(2),
top_p: z.number().min(0).max(1),
```

`instructions` is typed `z.string()` without `.min(1)`, so the UI will let the user save an empty instructions field, but the agent will not work.

### Defaults (file: `AgentFormPage.tsx:292-342`)

- `temperature: 1`, `top_p: 1`
- `allow_chat: true`
- `persist_conversation: true`
- `persist_user_history: true`
- `prompt_mode: "Local"`
- `enable_multi_run: false`
- `inject_conversation_data: true`
- `max_upload_size_mb: 25`

### Tab-by-tab assessment

#### General

File: `frontend/src/components/agent/GeneralTab.tsx`

- **Agent Name** plain, with placeholder `my-agent` (developer-ish example but acceptable).
- **Provider / Model** are link selects; descriptions mention OpenAI, OpenRouter, GPT-4-turbo — okay for P2.
- **Temperature** (`GeneralTab.tsx:163-169`):
  ```tsx
  <FormLabel>Temperature: {field.value}</FormLabel>
  ...
  <FormDescription>What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.</FormDescription>
  ```
  Jargon: "sampling temperature." No presets (Creative / Balanced / Precise). P2 can guess, P1 will not know what to pick.
- **Top P** (`GeneralTab.tsx:179-187`):
  ```tsx
  <FormLabel>Top P: {field.value}</FormLabel>
  ...
  {`An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of the tokens with top_p probability mass...`}
  ```
  Jargon: "nucleus sampling," "probability mass." The description admits "alter this or temperature but not both," yet the UI exposes both sliders with no guard.
- **Prompt Mode** Local/Template (`GeneralTab.tsx:202-225`): reasonably explained.
- **Instructions** textarea is the core prompt; description calls it "system prompt" (mild jargon).
- **Prompt Caching** section (`GeneralTab.tsx:269-362`): toggles plus `cache_control_type` (Auto/Ephemeral), Cache System Message, Cache Conversation History. DeepSeek/Anthropic specifics; P2 will skip, P1 will be lost.

#### Behavior

File: `frontend/src/components/agent/BehaviorTab.tsx`

- **Allow Chat**, **Persist History**, **Persist per User (Doc/Schedule)**, **Enable Multi Run** have decent descriptions.
- Cross-dependency is handled with toast warnings (`BehaviorTab.tsx:95-104`):
  ```tsx
  if (checked && !persistConversationEnabled) {
    toast.warning('Turn on Persist History before enabling chat.')
    return
  }
  ```
  This is discoverable only by trying; the UI does not visually disable the switch or explain the dependency inline.
- **Default Plan** table appears only if `enable_multi_run` is on; columns `instruction`, `output_ref` are low-level.

#### Triggers

File: `frontend/src/components/agent/TriggersTab.tsx`

- List-only tab. Columns: Type, Details, Status, Last Run, Next Run. Empty state says "No triggers added yet." Fine for P2.

#### Tools & MCP

File: `frontend/src/components/agent/ToolsTab.tsx`

- Section title "Tools" with description: "The set of tools this agent is allowed to use to interact with the system." Good.
- Section title "Model Context Protocol (MCP)" (`ToolsTab.tsx:218`) — acronym label; description at least explains "Connect to external MCP servers for additional tool capabilities."
- Empty-state copy is friendly: "Add tools to let this agent query data, run APIs, or call other agents."

#### Knowledge

File: `frontend/src/components/agent/KnowledgeTab.tsx`

- Empty state: "Link knowledge sources so this agent can retrieve relevant context from indexed documents." Clear.
- Mode badge shows `Mandatory` / `Optional` with `Priority` and token budget — P2 can infer.

#### Permissions

File: `frontend/src/components/agent/PermissionsTab.tsx`

- Description is excellent (`PermissionsTab.tsx:38-41`):
  ```tsx
  Configure who can run this agent. If both lists are empty, any authenticated user can access it.
  Otherwise access is limited to the owner, selected users, or users with selected roles.
  ```
- **Allow Guest API Access** is clearly explained.

#### Advanced Settings

File: `frontend/src/components/agent/AdvancedTab.tsx`

This tab is the biggest friction surface:

- **Context Strategy** (`AdvancedTab.tsx:87-109`): options `None`, `Summarize`, `FIFO`. Description: "Choose 'Summarize' to compress old messages via an LLM, or 'FIFO' to simply drop the oldest messages." P2 can follow; P1 may not know what FIFO means.
- **History Limit** / **Max Turns** / **Max Knowledge Tokens** / **Max Context Characters** — numeric fields with terse descriptions. "Consecutive actions in a single run" for Max Turns is accurate but abstract.
- **Summary Ratio** (`AdvancedTab.tsx:201-220`): "Fraction of history to compress (e.g., 0.7 = 70%)." Requires understanding the summarization pipeline.
- **Summary Model**, **Summary Prompt Mode/Template/Version Lock**, **Local Prompt** — all template-management concepts.
- **Conversation Data** section (`AdvancedTab.tsx:416-516`): "Allow Conversation Data Management," "Inject Conversation Data into Prompt," "Context Bloat" (jargon), API Permission Read/Write.
- **Huf UI** section (`AdvancedTab.tsx:519-571`): Agent color hex input, Show Tool Execution Details.
- **Model Modality Settings** (`AdvancedTab.tsx:574-687`): image_generation_model, tts_model, tts_voice, stt_model. Labels come from `data/ai.ts` but are still model-modality concepts.
- **Document Upload** (`AdvancedTab.tsx:689-765`): Allow File Upload, Enable OCR, Max Upload Size (MB).

### Minimum decisions to create a working chat agent

Strictly required by validation:
1. Agent Name
2. Provider
3. Model

Practically required for the agent to answer anything:
4. Instructions (or Prompt Template selection in Template mode)

`allow_chat` and `persist_conversation` default to `true`, so no extra decisions are needed to make it chat-enabled. A P2 can create a basic chat agent in **4 decisions** if they ignore the rest. However, the form does not guide them to ignore the rest — every advanced option is visible on tabs 1, 2, and 7.

> Verdict for W2: P2 can create a basic chat agent without docs, but the form drowns them in LLM/infra jargon and does not progressively disclose advanced options. P1 would be lost.

---

## W3. Tools & Triggers

### Adding a tool

File: `frontend/src/components/tools/SelectToolsModal.tsx:250-391`, `ToolFormModal.tsx`, `ToolCreationForm.tsx`.

Templates are presented in plain language (`frontend/src/config/toolTemplates.json:1-69`):

| Template | Description |
|----------|-------------|
| Document Operation | Read, create, update, or list records from your Frappe database |
| External API Request | Connect to third-party services via HTTP/REST |
| Platform Utility | Built-in capabilities like Speech-to-Text, Canvas operations |
| Run AI Agent | Delegate a task to another specialized AI Agent |
| Custom Script / Function | Execute a Python function or custom script |

So the **entry point** is friendly. Once inside the form, the vocabulary becomes technical:

- Operation Type list (`ToolCreationForm.tsx:516-545`) uses raw tool type names:
  - `Get Document`, `Create Document`, `Get List`, `Attach File to Document`, `Get Report Result`, `Set Value`, `GET`, `POST`, `Run Agent`, `Custom Function`, `App Provided`...
- **Custom Function** path (`ToolCreationForm.tsx:601-619`):
  ```tsx
  <FormLabel>Function Path</FormLabel>
  <Input placeholder="e.g., my_app.api.my_function" ... />
  ```
- **Fetch Params from Code** button (`ToolCreationForm.tsx:759-767`) requires the user to know a Python dotted path and assumes they have backend code.
- Parameters table uses `fieldname`, `description`, `type`, `required` (`ToolCreationForm.tsx:318-384`); editing a parameter opens a card with JSON-schema concerns.
- JSON editors are exposed:
  - "Parameters JSON schema preview" (`ToolCreationForm.tsx:831-835`)
  - "Function Def" tab (`ToolCreationForm.tsx:975-983`) shows raw function-definition JSON.
  - For GET/POST tools: HTTP Headers JSON (`ToolCreationForm.tsx:684-740`).
  - In the flow builder HTTP node: Headers (JSON) and Body (JSON) (`RightSidebar.tsx:896-925`).

For **P2**, the Document Operation / GET / POST templates are usable if they stay in the guided fields (Reference DocType, Base URL). The moment they need custom parameters or a custom function, the form becomes code-facing.

For **P1**, even the concept of "Reference DocType" assumes they know what a DocType is.

### Adding a trigger

Agent trigger form: `frontend/src/components/agent/TriggerModal.tsx` + `TriggerFieldsConfig.tsx`.

Trigger types (`TriggerModal.tsx:72-73`):

```ts
trigger_type: z.enum(['Schedule', 'Doc Event', 'Webhook', 'App Event', 'Manual']),
```

- **Schedule** (`TriggerFieldsConfig.tsx:23-40`): Interval (Hourly/Daily/Weekly/Monthly/Yearly), Count. Plain enough.
- **Doc Event** (`TriggerFieldsConfig.tsx:41-80`):
  ```ts
  options: [
    'before_insert', 'after_insert', 'validate', 'before_save', 'after_save',
    'before_submit', 'on_submit', 'on_update', 'after_submit', 'on_cancel',
    'before_rename', 'after_rename', 'on_trash', 'after_delete'
  ]
  ```
  These are raw Frappe lifecycle hook names. No plain-language mapping (e.g., "after a document is saved").
  - Condition field label is `"Condition (Python)"` with placeholder `"Use 'doc' to reference the document"` — direct code.
- **Webhook** asks for Slug + Key; acceptable for P2.
- **App Event** asks for App Name + Event Name; abstract.
- **Manual** is explained well: "Manual trigger can be run from workflows or flows. No configuration required."

Flow builder triggers (`frontend/src/components/modals/NodeSelectionModal.tsx:153-164`, `frontend/src/types/flow.types.ts:31-37`) also use raw DocEvent vocabulary:

```ts
export type DocEventType =
  | 'save'
  | 'update'
  | 'delete'
  | 'before-save'
  | 'before-update'
  | 'before-delete';
```

> Verdict for W3: Tool creation has a friendly template picker but quickly exposes JSON, function paths, and schema previews. Triggers are full of raw Frappe hook vocabulary and a Python condition editor. P2 can handle schedule/webhook triggers and basic CRUD tools; everything else is expert territory.

---

## W4. Chat & Results

### Chat interface

File: `frontend/src/pages/ChatPageV2.tsx`, `frontend/src/components/chat/ChatMessageList.tsx`, `frontend/src/components/chat/ChatMessage.tsx`.

- The chat page is clean: conversation list on the left, message stream on the right.
- Messages render with `ai-elements` primitives (`Message`, `MessageContent`), support markdown/artifacts, images, video, audio, attachments.
- Tool calls are rendered as collapsible `Tool` cards when `show_tool_execution_details` is enabled (`ChatMessage.tsx:105-121`).
- Status state is internal (`'submitted' | 'streaming' | 'ready' | 'error'`) and only surfaced as loading dots, not as user-facing labels.
- There is a **model-mismatch warning** (`ChatMessageList.tsx:42-81`) if the conversation's model differs from the agent's current model — a nice guard, but the warning text is not visible in the snippets; it may be too subtle.

### Executions list

File: `frontend/src/pages/Executions.tsx:31-37`, `149-155`, `168-253`

Status dot mapping:

```ts
if (normalized === 'success') return { variant: 'ok', label: status || 'Success' };
if (normalized === 'failed') return { variant: 'fail', label: status || 'Failed' };
if (normalized === 'queued') return { variant: 'idle', label: status || 'Queued' };
return { variant: 'run', label: status || 'Started' };
```

Columns: Agent, Run ID, Status, Duration, Started.

Status filter options (`Executions.tsx:149-155`): All Status, Started, Queued, Success, Failed.

The labels are human enough, but the page title "Executions" and column "Run ID" are still system-log flavored.

### Run detail

File: `frontend/src/pages/AgentRunDetailPage.tsx:103-483`

- Overview shows Agent, Provider, Model, Status, Started, Duration — clear.
- **Tokens & Cost** section (`AgentRunDetailPage.tsx:352-382`):
  ```tsx
  <span className="text-steel">Input Tokens</span>
  <span className="text-steel">Output Tokens</span>
  <span className="text-steel">Total Tokens</span>
  <span className="text-steel">Cost</span>
  ```
  Cost is shown as `$${run.cost.toFixed(6)}`. Six decimal places is developer precision; P1 would prefer a rounded currency display.
- **Prompt** and **Response** cards are readable.
- **Artifacts** section is labeled "Context artifacts recorded for this run" — artifact is a technical term.
- **Missing:** the page does **not** display `error_message`. The detail view shows status `Failed` but gives the user no explanation of why. `AgentRunDoc` includes `error_message`, yet the page never renders it.
- Child runs table is titled "Agent Orchestration" (`AgentRunDetailPage.tsx:421-426`) — "orchestration" is P2+ jargon.

> Verdict for W4: Chat is the most polished surface. Executions and run detail are mostly readable, but cost precision, "orchestration," and the missing error explanation hurt P1 comprehension.

---

## W5. Flows Builder

Files: `frontend/src/components/FlowCanvas.tsx`, `frontend/src/components/RightSidebar.tsx`, `frontend/src/components/modals/NodeSelectionModal.tsx`, `frontend/src/pages/FlowCanvasPage.tsx`, `frontend/src/components/modals/FlowSettingsModal.tsx`.

### What P2 sees

- Empty canvas with a single "Add Trigger" button.
- Trigger picker uses plain labels: Webhook, Schedule, Human Input, Data (`data/triggers.ts:1-36`).
- Action picker uses plain labels: Run Agent, Call Tool, LLM Router, Condition (If/Else), Loop, Human in Loop, Transform Data, Execute Code, Send Email, Call Webhook (`data/actions.ts:1-120`).
- Nodes render with icons and status badges; hovering shows a `+` button to add the next node.
- The right sidebar title changes contextually: "Node Settings" / "Edge Settings" / "Flow Settings".

### Could P2 build a simple approval flow?

A trigger → **Human in Loop** → end flow is conceptually possible, but the configuration surface is not fully guided:

- **Human in Loop** node (`RightSidebar.tsx:688-810`) exposes:
  - `approval_type`: role | user
  - `assigned_role` / `assigned_user`
  - `store_decision_in_context` placeholder `"e.g., approval_result"`
  - No explanation of how the approver is notified or where they approve.
- To branch on the decision, P2 must add a **Condition (If/Else)** node or an **Expression** edge.

### Concepts that leak

1. **Edges / Edge Configuration** (`RightSidebar.tsx:386-450`)
   - Edge Type options: `always`, `on_success`, `on_failure`, `expression`.
   - When `expression` is selected, a free-text "Condition Expression" field appears with placeholder:
     ```tsx
     placeholder='context["status"] == "approved"'
     ```
     P2 must write Python-like expressions against a `context` object. There is no visual rule builder.

2. **Condition node** (`RightSidebar.tsx:812-855`)
   - Same expression field, plus explicit `true_node` / `false_node` Node IDs.
   - Description: "Evaluates a boolean expression against context. Routes to True or False branch node."

3. **Loop node** (`RightSidebar.tsx:1045-1112`)
   - Requires typing context keys (`iterate_over`, `item_key`, `index_key`) and Node IDs for `loop_node` and `done_node`.
   - Example placeholders: `items`, `users`, `Node to execute per iteration`.

4. **Flow Settings** (`FlowSettingsModal.tsx:161-187`)
   - **Execution Mode**: `Normal` / `Agentic`. No explanation in the modal of what Agentic does.
   - **Max Hops**: default 100, described nowhere in the UI. A P2 will not know what a "hop" is.

5. **Fallback JSON viewer** (`RightSidebar.tsx:1115-1125`)
   - For action types without a dedicated form, the sidebar shows raw JSON:
     ```tsx
     <code className="text-xs text-muted-foreground font-mono block overflow-x-auto">
       {JSON.stringify(config, null, 2)}
     </code>
     ```

6. **Router / LLM Router** (`RightSidebar.tsx:649-686`)
   - "Routing Agent" select and "conversation_mode" (`flow_shared` / `isolated`). The concept of a routing agent is advanced.

7. **HTTP request node** (`RightSidebar.tsx:857-925`)
   - Headers and Body are JSON textareas with manual `JSON.parse` / catch behavior. P2 must type valid JSON.

> Verdict for W5: P2 could drag out a trigger → human approval → end shape, but configuring branching, conditions, loops, or HTTP nodes requires writing code-like expressions and JSON. The builder is not truly no-code yet.

---

## W6. Top Friction Ranking

Ranked by severity for P1 / P2 combined, with file:line evidence and the cheapest fix.

| # | Friction | Evidence | Cheapest fix |
|---|----------|----------|--------------|
| 1 | Hub sidebar labels "Executions" and "AI Providers" and Settings submenu items (MCP Servers, Console, Integration Services) are dev/sysadmin vocabulary. | `app-sidebar.tsx:83`, `118`, `130`, `148`, `HubSimplePage.tsx:50-57` | Rename to plain labels: Run History, AI Connections, API Servers, Test Console, App Connections; add one-line subtitles. |
| 2 | Agent form surfaces two opaque LLM sliders (Temperature, Top P) with no presets or hide option. | `GeneralTab.tsx:163-188` | Add a "Response style" segmented control (Precise / Balanced / Creative) that sets both values; hide the sliders behind an "Advanced" disclosure. |
| 3 | Doc Event triggers expose raw Frappe hook names (`after_insert`, `on_submit`) and a Python condition editor. | `TriggerFieldsConfig.tsx:54-69`, `TriggerModal.tsx:71-103` | Map hook names to plain labels ("After a document is saved", "When a document is submitted") and provide a field-based condition builder. |
| 4 | Tool creation form exposes JSON schema preview, Function Path, and "Fetch Params from Code" to all users. | `ToolCreationForm.tsx:234-267`, `831-835`, `975-983` | Move JSON/function-path features behind a "Developer view" toggle; default to guided fields only. |
| 5 | Agent Advanced Settings tab dumps 20+ infra/LLM options without progressive disclosure. | `AdvancedTab.tsx:80-765` | Hide most options under expandable sections or an "Advanced" switch; default to sensible system values. |
| 6 | Run detail page shows status Failed but does not render `error_message`, leaving P1 without an explanation. | `AgentRunDetailPage.tsx:308-415` | Add an "Error" card that displays `run.error_message` when status is Failed. |
| 7 | Flow builder edges/conditions require writing `context["status"] == "approved"` with no guidance. | `RightSidebar.tsx:438-449`, `812-832` | Add a visual condition builder (pick context key, operator, value) and populate common examples. |
| 8 | Flow "Agentic" mode and "Max Hops" are unexplained in the Flow Settings modal. | `FlowSettingsModal.tsx:161-187` | Add inline help text: "Agentic lets an AI pick the next node"; rename Max Hops to "Maximum steps" with tooltip. |
| 9 | Human-in-loop node exposes raw context-variable names (`store_decision_in_context`) and does not explain how approvers are notified. | `RightSidebar.tsx:688-810` | Rename to "Save decision as" with helper text; add a link to the approval inbox or notification settings. |
| 10 | Hub slash commands advertise `/settings` and `/cost` but route to broken/unimplemented pages. | `HubSimplePage.tsx:161-164`, `App.tsx:344-355` | Fix routes or remove misleading commands until the pages exist. |

---

## Overall verdict

**<verdict: EXPERT-ONLY>**

The chat surface and the top-level template pickers are friendly, but the core builder surfaces (agent advanced settings, custom tools, triggers, flow conditions/loops) consistently expose backend concepts, JSON editors, raw Frappe hook names, and code-like expressions. A non-technical business user (P1) cannot confidently build or debug an agent or flow. A functional consultant (P2) can create a basic chat agent and a simple schedule trigger, but anything involving branching, custom tools, or failure diagnosis requires reading docs or asking a developer.
