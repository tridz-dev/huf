# RFC: Agent Form Refactoring — Schema-Driven Architecture

**Status**: Proposal
**Author**: AI-assisted analysis
**Date**: 2026-02-20
**Scope**: `frontend/src/pages/AgentFormPage.tsx` and `frontend/src/components/agent/*`

---

## 1. Executive Summary

The Agent form is the most complex UI surface in Huf. At ~900 lines in the orchestrator alone (`AgentFormPage.tsx`) plus ~1,740 lines across child components, it works today but is approaching a complexity threshold that will make it expensive to extend, localize, and maintain. This document captures the current implementation, its strengths and weaknesses, and proposes a schema-driven refactor inspired by patterns from Frappe, Strapi, Directus, n8n, and other large open-source form-heavy projects.

---

## 2. Current Implementation

### 2.1 File Map

| File | Lines | Responsibility |
|------|-------|----------------|
| `pages/AgentFormPage.tsx` | 896 | God component: form init, tab routing, data loading, submission, change detection, 10+ handlers, 3 modals |
| `components/agent/types.ts` | 19 | Zod schema + inferred type |
| `components/agent/GeneralTab.tsx` | 213 | LLM config fields + instructions textarea |
| `components/agent/BehaviorTab.tsx` | 135 | 4 boolean switch fields with cross-field logic |
| `components/agent/TriggersTab.tsx` | 159 | Trigger list/table (no form fields) |
| `components/agent/ToolsTab.tsx` | 266 | Tool + MCP server lists (no form fields) |
| `components/agent/AgentHeader.tsx` | 153 | Inline agent name edit, status badges, action buttons |
| `components/agent/InstructionsTextarea.tsx` | 187 | Dual-mode (form/standalone) textarea with expand modal |
| `components/agent/TriggerModal.tsx` | 279 | Separate form with inline Zod schema |
| `components/agent/TriggerFieldsConfig.tsx` | 149 | JSON-ish config for trigger type fields (already schema-driven!) |
| `components/agent/TriggerFieldsRenderer.tsx` | 180 | Renders fields from TriggerFieldsConfig |
| `utils/formValidation.ts` | 123 | Hidden-tab error detection + submit handler factory |

### 2.2 Data Flow

```
AgentFormPage (orchestrator)
  ├── useForm<AgentFormValues>() with zodResolver
  ├── 24 useState hooks (!)
  ├── 6 useEffect hooks
  ├── 12+ handler functions
  ├── loads: providers, models, toolTypes, triggers, docTypes, triggerTypes, agent, tools, mcpServers
  │
  ├── <AgentHeader form={form} ...12 props />
  ├── <Form>
  │     <Tabs>
  │       <GeneralTab form={form} ...5 props />
  │       <BehaviorTab form={form} />
  │       <TriggersTab ...10 props />
  │       <ToolsTab ...10 props />
  │     </Tabs>
  │   </Form>
  ├── <TriggerModal ...8 props />
  ├── <SelectToolsModal ...4 props />
  └── <SelectMCPServersModal ...4 props />
```

### 2.3 Zod Schema (current)

```typescript
// components/agent/types.ts — 12 flat fields
export const agentFormSchema = z.object({
  agent_name: z.string().min(1, 'Agent name is required'),
  provider: z.string().min(1, 'Provider is required'),
  model: z.string().min(1, 'Model is required'),
  temperature: z.number().min(0).max(2),
  top_p: z.number().min(0).max(1),
  disabled: z.boolean(),
  allow_chat: z.boolean(),
  persist_conversation: z.boolean(),
  persist_user_history: z.boolean(),
  enable_multi_run: z.boolean(),
  description: z.string().optional(),
  instructions: z.string(),
});
```

---

## 3. Observations

### 3.1 What Works Well

1. **TriggerFieldsConfig is already schema-driven.** The trigger subsystem (`TriggerFieldsConfig.tsx` + `TriggerFieldsRenderer.tsx`) proves the pattern: a JSON config describes fields, types, options, and required state; a generic renderer maps them to UI components. This is the right direction — it just hasn't been applied to the main form.

2. **Tab config as single source of truth.** The `tabConfig` object in `AgentFormPage` maps tab keys → labels + fields. Good instinct, but it only drives tab rendering — not field rendering or validation.

3. **Zod + React Hook Form.** Solid library choices. Zod schemas can be generated programmatically from JSON configs, which is the bridge to schema-driven forms.

4. **Composable tab components.** Each tab is its own component with a clear props interface.

5. **Hidden-tab error detection.** `formValidation.ts` checks tabs the user hasn't visited. Smart UX that many projects skip.

6. **Change detection beyond form dirtyness.** Tracking tools, MCP servers, and disabled state separately from RHF's built-in `isDirty` shows careful UX thinking.

### 3.2 What Needs Attention

#### A. God Component Anti-Pattern (Critical)

`AgentFormPage.tsx` is 896 lines with **24 `useState` hooks** and **12+ handler functions**. It's the form orchestrator, data fetcher, modal controller, change detector, and submission handler all in one. This is the single biggest maintenance risk.

**Evidence:**
- `loading`, `saving`, `deletingTrigger`, `optimizingPrompt`, `runningTest`, `mcpLoading` — 6 loading states
- `providers`, `models`, `triggers`, `docTypes`, `triggerTypes`, `toolTypes` — 6 reference data states
- `selectedTools`, `initialTools`, `mcpServers`, `initialMcpServers`, `initialDisabled` — 5 change-tracking states
- `showTriggerModal`, `editingTrigger`, `showToolsModal`, `showMCPServersModal` — 4 modal states
- `triggerFilter`, `triggerStatusFilter` — 2 filter states (owned by parent but used only by TriggersTab)

Comparison: In n8n's node editor, the form component delegates data fetching to composable hooks and modal state to a store. In Strapi's content manager, the edit page is ~200 lines because field rendering is entirely schema-driven.

#### B. Duplicated Data Transformation Logic

The Frappe `0/1 ↔ boolean` conversion appears in **3 separate places**:
1. Loading agent data (lines 286-299) — `data.disabled === 1` → `true`
2. After create success (lines 428-441) — same conversion repeated
3. On submit (lines 399-421) — `values.disabled ? 1 : 0` reverse conversion

Similarly, the MCP server enrichment logic (fetch each server, merge fields) is **copy-pasted** between the initial load (lines 336-376) and the post-save reload (lines 471-512) — ~40 lines duplicated verbatim.

#### C. Schema and UI Are Decoupled

The Zod schema knows field names and validation rules. The tab components know labels, descriptions, placeholders, and layout. The `tabConfig` knows which fields belong to which tab. These three sources of truth are maintained independently — adding a field requires edits in **4+ files**:
1. `types.ts` — add to Zod schema
2. `AgentFormPage.tsx` — add to `defaultValues`, `tabConfig`, `form.reset()` (x2), `onSubmit`, and `AgentDoc` mapping
3. Tab component — add the JSX field rendering
4. `agent.types.ts` — add to `AgentDoc` interface

#### D. No i18n Infrastructure

All UI strings are hardcoded English:
- 40+ form labels and descriptions in tab components
- 30+ toast messages in AgentFormPage
- Error messages in Zod schemas ("Agent name is required")
- Trigger field labels in TriggerFieldsConfig

There is **zero** i18n setup in the frontend (no `react-i18next`, no locale files, no `t()` calls). The backend Python uses `_()` markers, but the frontend doesn't.

#### E. Prop Drilling

`AgentFormPage` passes the entire `form` object (or 10+ individual props) down to every child. Examples:
- `AgentHeader` receives 13 props
- `TriggersTab` receives 10 props
- `ToolsTab` receives 10 props

This creates coupling: every child's interface changes when the parent adds a feature.

#### F. Cross-Field Validation Logic Lives in Components

`BehaviorTab` contains business rules in `onCheckedChange` handlers:
- "Allow Chat requires Persist Conversation"
- "Multi Run disables Allow Chat"
- "Disabling Persist Conversation auto-disables Allow Chat"

These rules are implicit in JSX event handlers rather than declared in the schema. They can't be reused, tested independently, or surfaced in a schema-driven renderer.

#### G. Mixed Concerns in Tab Components

`ToolsTab` and `TriggersTab` are not form tabs — they're list management UIs. They don't use `form.control` or render `FormField`s. They're placed inside `<Form>` and `<Tabs>` for navigation but are architecturally different from `GeneralTab` and `BehaviorTab`. This conflation makes the `tabConfig.fields` array misleading (empty `[]` for non-form tabs).

---

## 4. Criticism: What Large Open-Source Projects Do Differently

### 4.1 Frappe Framework (the project's own backend)

Frappe renders forms entirely from JSON DocType definitions stored in the database. A field definition looks like:

```json
{
  "fieldname": "agent_name",
  "fieldtype": "Data",
  "label": "Agent Name",
  "reqd": 1,
  "description": "Unique identifier for this agent",
  "in_list_view": 1,
  "section": "general"
}
```

The framework handles rendering, validation, and i18n. **Huf's frontend should mirror this pattern** — you're already doing it with `TriggerFieldsConfig`; now generalize it.

### 4.2 Strapi (Content Manager)

Strapi's edit view reads a schema from the server (content-type definitions) and uses a generic `<GenericInput>` component that switches on `fieldType`. Adding a field is a schema change, not a code change. Their form pages are typically <200 lines.

### 4.3 n8n (Node Configuration)

n8n defines every node's parameters as a JSON array:

```json
{
  "displayName": "Temperature",
  "name": "temperature",
  "type": "number",
  "default": 1,
  "typeOptions": { "minValue": 0, "maxValue": 2, "numberStepSize": 0.1 },
  "description": "Controls randomness of output"
}
```

A single renderer handles all field types. Conditional display, validation, and i18n are driven by the schema.

### 4.4 Directus (Item Detail)

Directus derives its entire edit interface from collection schemas. Field rendering, layout, validation, and translations are all schema-driven. The form page itself is a thin shell.

### 4.5 Common Pattern

All these projects share one principle: **the form schema is the single source of truth** for field definitions, validation, layout, labels, and descriptions. The rendering is generic. The form page is a thin orchestrator.

---

## 5. Proposed Refactoring Plan

### Phase 1: Extract Hooks (Reduce God Component)

**Goal**: Bring `AgentFormPage` from ~900 lines to ~200 lines.

```
hooks/
  useAgentForm.ts          — form init, default values, Zod resolver
  useAgentData.ts          — data loading (providers, models, tools, etc.)
  useAgentSubmit.ts        — submit handler + Frappe boolean conversion
  useAgentChangeDetection.ts — tools/MCP/disabled dirty tracking
  useAgentModals.ts        — modal open/close/editing state
  useTriggerActions.ts     — CRUD for triggers
  useMCPActions.ts         — MCP server add/remove/toggle/sync
```

**Before** (AgentFormPage):
```tsx
// 24 useState, 6 useEffect, 12 handlers
export function AgentFormPage() { ... 896 lines ... }
```

**After**:
```tsx
export function AgentFormPage() {
  const { id } = useParams();
  const isNew = id === 'new';

  const form = useAgentForm();
  const { providers, models, toolTypes, loading } = useAgentData(id, form);
  const { selectedTools, mcpServers, showSaveButton, ...toolActions } = useAgentChangeDetection(form, isNew);
  const { handleSubmit } = useAgentSubmit(form, id, isNew, selectedTools, mcpServers);
  const modals = useAgentModals();
  const triggerActions = useTriggerActions(id);

  if (loading) return <LoadingState />;

  return (
    <AgentFormShell
      form={form}
      tabs={tabConfig}
      header={<AgentHeader ... />}
      modals={<AgentModals ... />}
      onSubmit={handleSubmit}
    />
  );
}
```

This is **pure refactoring** — no behavior change, no schema-driven rendering yet. Safe first step.

### Phase 2: Schema-Driven Field Definitions

**Goal**: Define all agent fields in a single JSON-like config. Generate Zod schemas, default values, and rendering from it.

```typescript
// schema/agentFormSchema.ts

import type { FieldDefinition } from '@/lib/form-schema';

export const agentFields: FieldDefinition[] = [
  // ── General Tab ──
  {
    name: 'agent_name',
    type: 'text',
    label: 'agent.fields.agent_name.label',     // i18n key
    description: 'agent.fields.agent_name.desc',
    placeholder: 'my-agent',
    required: true,
    tab: 'general',
    section: 'identity',
  },
  {
    name: 'description',
    type: 'textarea',
    label: 'agent.fields.description.label',
    tab: 'general',
    section: 'identity',
    collapsible: true,   // render in accordion
  },
  {
    name: 'provider',
    type: 'select',
    label: 'agent.fields.provider.label',
    required: true,
    tab: 'general',
    section: 'llm_config',
    optionsFrom: 'providers',   // resolved at runtime
    onChange: 'clearModel',      // named side-effect
  },
  {
    name: 'model',
    type: 'select',
    label: 'agent.fields.model.label',
    required: true,
    tab: 'general',
    section: 'llm_config',
    optionsFrom: 'models',
    dependsOn: 'provider',      // disabled until provider set
  },
  {
    name: 'temperature',
    type: 'slider',
    label: 'agent.fields.temperature.label',
    tab: 'general',
    section: 'llm_config',
    min: 0,
    max: 2,
    step: 0.1,
    default: 1,
  },
  {
    name: 'top_p',
    type: 'slider',
    label: 'agent.fields.top_p.label',
    tab: 'general',
    section: 'llm_config',
    min: 0,
    max: 1,
    step: 0.05,
    default: 1,
  },
  {
    name: 'instructions',
    type: 'code',    // renders InstructionsTextarea
    label: 'agent.fields.instructions.label',
    tab: 'general',
    section: 'instructions',
    fullWidth: true,
  },

  // ── Behavior Tab ──
  {
    name: 'allow_chat',
    type: 'switch',
    label: 'agent.fields.allow_chat.label',
    description: 'agent.fields.allow_chat.desc',
    tab: 'behavior',
    default: true,
    disabledWhen: { enable_multi_run: true },
    requiresTrue: ['persist_conversation'],
  },
  {
    name: 'persist_conversation',
    type: 'switch',
    label: 'agent.fields.persist_conversation.label',
    description: 'agent.fields.persist_conversation.desc',
    tab: 'behavior',
    default: true,
    onFalse: { allow_chat: false },
  },
  {
    name: 'persist_user_history',
    type: 'switch',
    label: 'agent.fields.persist_user_history.label',
    description: 'agent.fields.persist_user_history.desc',
    tab: 'behavior',
    default: true,
  },
  {
    name: 'enable_multi_run',
    type: 'switch',
    label: 'agent.fields.enable_multi_run.label',
    description: 'agent.fields.enable_multi_run.desc',
    tab: 'behavior',
    default: false,
    onTrue: { allow_chat: false },
  },
];
```

**Utilities derived from this config:**

```typescript
// lib/form-schema.ts

// 1. Generate Zod schema from field definitions
export function buildZodSchema(fields: FieldDefinition[]): z.ZodObject<any> { ... }

// 2. Generate default values
export function buildDefaults(fields: FieldDefinition[]): Record<string, any> { ... }

// 3. Generate tab config (replaces manual tabConfig)
export function buildTabConfig(fields: FieldDefinition[]): TabConfig { ... }

// 4. Get fields for a tab
export function getTabFields(fields: FieldDefinition[], tab: string): FieldDefinition[] { ... }
```

### Phase 3: Generic Field Renderer

**Goal**: A single component that renders any `FieldDefinition` to the correct shadcn/ui widget.

```typescript
// components/form/SchemaField.tsx

export function SchemaField({ field, form, context }: SchemaFieldProps) {
  const { t } = useTranslation();

  switch (field.type) {
    case 'text':
      return (
        <FormField control={form.control} name={field.name} render={({ field: rhf }) => (
          <FormItem>
            <FormLabel>{t(field.label)}</FormLabel>
            <FormControl><Input placeholder={field.placeholder} {...rhf} /></FormControl>
            {field.description && <FormDescription>{t(field.description)}</FormDescription>}
            <FormMessage />
          </FormItem>
        )} />
      );
    case 'select':
      return <SchemaSelectField ... />;
    case 'slider':
      return <SchemaSliderField ... />;
    case 'switch':
      return <SchemaSwitchField ... />;
    case 'textarea':
      return <SchemaTextareaField ... />;
    case 'code':
      return <SchemaCodeField ... />;   // wraps InstructionsTextarea
    default:
      return null;
  }
}
```

**Tab renderer:**

```typescript
// components/form/SchemaTab.tsx

export function SchemaTab({ fields, form, context }: SchemaTabProps) {
  const sections = groupBy(fields, 'section');

  return (
    <>
      {Object.entries(sections).map(([section, sectionFields]) => (
        <Card key={section}>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {sectionFields.map(field => (
              <SchemaField
                key={field.name}
                field={field}
                form={form}
                context={context}
                className={field.fullWidth ? 'sm:col-span-2' : undefined}
              />
            ))}
          </CardContent>
        </Card>
      ))}
    </>
  );
}
```

### Phase 4: i18n Integration

**Goal**: All user-facing strings go through `react-i18next`.

```
frontend/
  src/
    locales/
      en/
        common.json        — shared strings (Save, Cancel, Loading...)
        agent.json         — agent form labels, descriptions, errors
        triggers.json      — trigger-specific strings
        tools.json         — tool/MCP strings
      # future: fr/, de/, ja/, ar/, etc.
    lib/
      i18n.ts             — i18next init with lazy-loaded namespaces
```

**agent.json example:**

```json
{
  "fields": {
    "agent_name": {
      "label": "Agent Name",
      "desc": "Unique identifier for this agent",
      "placeholder": "my-agent",
      "error_required": "Agent name is required"
    },
    "temperature": {
      "label": "Temperature",
      "desc": "Controls randomness (0 = deterministic, 2 = creative)"
    },
    "allow_chat": {
      "label": "Allow Chat",
      "desc": "If checked, this agent can be interacted with in the Agent Chat window."
    }
  },
  "tabs": {
    "general": "General",
    "behavior": "Behavior",
    "triggers": "Triggers",
    "tools": "Tools & MCP"
  },
  "actions": {
    "save": "Save",
    "create": "Create",
    "saving": "Saving...",
    "creating": "Creating..."
  },
  "messages": {
    "created": "Agent created successfully!",
    "updated": "Agent updated successfully!",
    "create_failed": "Failed to create agent. Please try again.",
    "update_failed": "Failed to update agent. Please try again."
  }
}
```

**Zod error messages become i18n-aware:**

```typescript
function buildZodSchema(fields: FieldDefinition[], t: TFunction) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const field of fields) {
    if (field.type === 'text' || field.type === 'select') {
      let s = z.string();
      if (field.required) s = s.min(1, t(`${field.label}_required`) || `${field.name} is required`);
      shape[field.name] = field.required ? s : s.optional();
    }
    // ... other types
  }
  return z.object(shape);
}
```

### Phase 5: Centralize Frappe ↔ Form Transformations

**Goal**: Never hand-write `data.disabled === 1` again.

```typescript
// lib/frappe-form.ts

/**
 * Convert a Frappe document (0/1 booleans) to form values (true/false booleans)
 * driven by the field schema.
 */
export function docToFormValues(
  doc: Record<string, any>,
  fields: FieldDefinition[]
): Record<string, any> {
  const values: Record<string, any> = {};
  for (const field of fields) {
    const raw = doc[field.name];
    if (field.type === 'switch') {
      values[field.name] = raw === 1;
    } else {
      values[field.name] = raw ?? field.default ?? '';
    }
  }
  return values;
}

/**
 * Convert form values back to Frappe document format.
 */
export function formValuesToDoc(
  values: Record<string, any>,
  fields: FieldDefinition[]
): Record<string, any> {
  const doc: Record<string, any> = {};
  for (const field of fields) {
    const val = values[field.name];
    if (field.type === 'switch') {
      doc[field.name] = val ? 1 : 0;
    } else {
      doc[field.name] = val;
    }
  }
  return doc;
}
```

This eliminates the 3 places where boolean conversion is currently hardcoded.

---

## 6. Non-Form Tabs: Keep Separate

`TriggersTab` and `ToolsTab` are **not form tabs** — they manage lists of related records. The refactor should formalize this distinction:

```typescript
export const agentTabConfig = {
  general:  { type: 'form',    label: 'tabs.general',  component: null },     // rendered by SchemaTab
  behavior: { type: 'form',    label: 'tabs.behavior', component: null },     // rendered by SchemaTab
  triggers: { type: 'custom',  label: 'tabs.triggers', component: TriggersTab },
  tools:    { type: 'custom',  label: 'tabs.tools',    component: ToolsTab },
};
```

Form tabs use the generic renderer. Custom tabs keep their bespoke components. This makes the `fields: []` hack unnecessary.

---

## 7. Cross-Field Validation: Declarative Rules

Move business rules out of JSX event handlers and into the schema:

```typescript
// Current (BehaviorTab.tsx lines 39-48):
onCheckedChange={(checked) => {
  if (enableMultiRun) {
    toast.warning('Chat is not available for multi run agents right now.');
    return;
  }
  if (checked && !persistConversationEnabled) {
    toast.warning('Turn on Persist History before enabling chat.');
    return;
  }
  field.onChange(checked);
}}

// Proposed (in field definition):
{
  name: 'allow_chat',
  type: 'switch',
  disabledWhen: { enable_multi_run: true },
  disabledMessage: 'agent.fields.allow_chat.disabled_multi_run',
  requiresTrue: ['persist_conversation'],
  requiresMessage: 'agent.fields.allow_chat.requires_persist',
}
```

A `useCrossFieldRules(form, fields)` hook interprets these declarations at runtime, calling `form.setValue()` and `toast.warning()` as needed. The rules become testable without rendering components.

---

## 8. Migration Strategy

| Phase | Effort | Risk | Behavior Change |
|-------|--------|------|-----------------|
| 1. Extract hooks | Small | Low | None — pure refactor |
| 2. Field schema definitions | Medium | Low | None — adds schema alongside existing code |
| 3. Generic field renderer | Medium | Medium | Replaces GeneralTab/BehaviorTab JSX |
| 4. i18n integration | Medium | Low | Strings become translatable |
| 5. Frappe transform centralization | Small | Low | None — removes duplication |

**Recommended order**: 1 → 5 → 2 → 3 → 4

Phase 1 and 5 are safe refactors that immediately reduce complexity. Phase 2 and 3 can be done incrementally (one tab at a time). Phase 4 can happen in parallel once the schema keys exist.

---

## 9. Adding a New Field: Before vs After

### Before (current — 4+ files, ~30 lines)

1. `types.ts`: Add to Zod schema
2. `AgentFormPage.tsx`: Add to `defaultValues`, both `form.reset()` blocks, `onSubmit` conversion, `tabConfig.fields`
3. `GeneralTab.tsx` or `BehaviorTab.tsx`: Add 15-20 lines of JSX
4. `agent.types.ts`: Add to `AgentDoc` interface

### After (proposed — 2 files, ~8 lines)

1. `schema/agentFormSchema.ts`: Add one `FieldDefinition` object (5 lines)
2. `agent.types.ts`: Add to `AgentDoc` interface (1 line)
3. `locales/en/agent.json`: Add label + description (2 lines)

Everything else (Zod schema, default values, tab assignment, rendering, Frappe conversion) is automatic.

---

## 10. Reference Implementations to Study

| Project | Pattern | Where to Look |
|---------|---------|---------------|
| **Frappe** | DocType JSON → form rendering | `frappe/public/js/frappe/form/` |
| **n8n** | Node parameter JSON → form rendering | `packages/editor-ui/src/components/ParameterInput*` |
| **Strapi** | Content-type schema → `GenericInput` | `packages/core/content-manager/admin/src/components/` |
| **Directus** | Collection schema → interface rendering | `app/src/interfaces/` |
| **React JSON Schema Form** | JSON Schema → React form | `@rjsf/core` (can be used directly or as inspiration) |
| **Formily** | Schema-driven forms for Ant Design/others | `@formily/react` (Alibaba's approach) |

---

## 11. Summary

The agent form is functional and well-thought-out in places (trigger config, hidden-tab errors, change detection). But it's at an inflection point: the god component pattern won't scale as fields grow, i18n is impossible without extracting strings, and every new field requires synchronized edits across 4+ files.

The recommended path:
1. **Immediately**: Extract custom hooks from `AgentFormPage` (Phase 1) — this alone halves the complexity
2. **Short-term**: Centralize Frappe transforms (Phase 5) — eliminates duplicated boolean conversion
3. **Medium-term**: Introduce `FieldDefinition` schema + generic renderer (Phases 2-3) — makes adding fields trivial
4. **When needed**: Add `react-i18next` with schema-driven i18n keys (Phase 4)

The trigger subsystem already proves the schema-driven pattern works in this codebase. Generalize it.
