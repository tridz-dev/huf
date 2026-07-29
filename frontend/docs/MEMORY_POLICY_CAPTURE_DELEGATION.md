# Memory Policy: Capture Delegation (`capture_mode` + `learning_agent`)

Status: **not implemented — planning doc for a follow-up PR**
Depends on: the base Memory Policy management UI (list/create/edit/delete).

## Why this was pulled out of the base UI PR

`Memory Policy.capture_mode` and `Memory Policy.learning_agent` exist as
doctype fields and were originally exposed in the policy edit form (Capture
Mode select: Manual / Agent Suggested / Automatic, plus a Learning Agent
picker). Auditing the runtime found **zero reads** of either field anywhere
outside the doctype and the seed data in `install.py` — choosing "Automatic"
in the UI silently behaved identically to "Manual". Shipping a control that
looks live but does nothing is worse than not shipping it, so both fields
were removed from the form for the base PR and are tracked here instead.

## What this feature is meant to do

A memory policy currently only supports two capture paths, both driven by
explicit tool calls from the conversation's own agent:

- `save_memory_record` called manually by the user, or
- `save_memory_record` called by the agent mid-conversation (if
  `allow_agent_write` permits it).

`capture_mode` + `learning_agent` add a third path: **background extraction**,
where memory formation isn't bounded by the main agent's context window or
per-turn cost.

- **`capture_mode = "Manual"`** (current, only implemented behavior): nothing
  changes — writes only happen via explicit tool calls.
- **`capture_mode = "Agent Suggested"`**: after a run completes, a background
  job reviews the transcript and proposes candidate memory records. These
  always land as `Draft`, regardless of `approval_required`, and need human
  approval before becoming active.
- **`capture_mode = "Automatic"`**: same background extraction, but records
  are subject to the policy's normal `approval_required` / `default_status`
  handling — no forced Draft.
- **`learning_agent`**: optional. The agent that runs the background
  extraction job. If unset, falls back to the conversation's own agent. This
  is what makes the feature "limitless" — a cheap, dedicated extraction agent
  can run over every conversation without the main agent's context or budget
  ever being touched.

## Implementation sketch (not yet built)

1. On Agent Run completion, if `capture_mode != "Manual"`, `frappe.enqueue` an
   extraction job (the codebase already uses this exact pattern extensively
   in `huf/ai/agent_integration.py` — `enqueue_after_commit=True`, etc.).
2. The job resolves the extraction agent: `policy.learning_agent` if set,
   else the conversation's agent.
3. It runs that agent over the transcript with an extraction-specific prompt
   and emits candidate records via the *existing* `save_memory_record` path —
   no new write path, no new permission model. This means all the write-
   permission and promotion enforcement already in `memory_tools.py`
   (`_can_write_memory`, `allowed_record_types`, `auto_promote_to_knowledge`,
   the promotion thresholds) applies unchanged.
4. `Agent Suggested` forces `status="Draft"` before calling
   `save_memory_record`, overriding whatever `default_status` would have set.
   `Automatic` does not override — it lets the existing `approval_required` /
   `default_status` logic in `save_memory_record` decide.

## Code / UI already written (removed from the base PR, for reuse here)

The following existed in the base UI branch and was reverted before merge.
It's a reasonable starting point, not a final design — in particular the
"Learning Agent" combobox and Capture Mode `<Select>` will need to move into
whatever container the tabs restructure below settles on.

`frontend/src/components/memory/memoryPolicyFormSchema.ts` (schema piece):

```ts
export const memoryCaptureModes = ['Manual', 'Agent Suggested', 'Automatic'] as const;
// ...
capture_mode: z.enum(memoryCaptureModes).default('Manual'),
learning_agent: z.string().optional(),
```

`frontend/src/components/memory/MemoryPolicyFields.tsx` (form fields):

```tsx
<FormField
  control={form.control}
  name="capture_mode"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Capture Mode</FormLabel>
      <Select value={field.value} onValueChange={field.onChange}>
        <FormControl>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
        </FormControl>
        <SelectContent>
          {memoryCaptureModes.map((mode) => (
            <SelectItem key={mode} value={mode}>
              {mode}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FormDescription>
        <span className="block"><strong>Manual</strong> — only explicit user or tool-call writes create memory.</span>
        <span className="block"><strong>Agent Suggested</strong> — the agent proposes memory records for approval.</span>
        <span className="block"><strong>Automatic</strong> — memory is extracted from conversations in the background.</span>
      </FormDescription>
      <FormMessage />
    </FormItem>
  )}
/>

<FormField
  control={form.control}
  name="learning_agent"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Learning Agent</FormLabel>
      <FormControl>
        <Combobox
          options={agentOptions}
          value={field.value}
          onValueChange={(v) => field.onChange(v || undefined)}
          placeholder="Use the conversation's agent"
          searchPlaceholder="Search agents..."
          emptyText="No agents found."
          linkTo={linkRoutes.agent}
        />
      </FormControl>
      <FormDescription>
        Optional dedicated agent that runs background memory extraction, instead of the
        conversation's own agent.
      </FormDescription>
      <FormMessage />
    </FormItem>
  )}
/>
```

`frontend/src/pages/MemoryPolicyFormPage.tsx` (map to/from form values):

```ts
// mapDocToFormValues
capture_mode: doc.capture_mode || 'Manual',
learning_agent: doc.learning_agent || undefined,

// onSubmit payload
capture_mode: values.capture_mode,
learning_agent: values.learning_agent || null,
```

`frontend/src/services/memoryPolicyApi.ts`: re-add `'capture_mode'` to
`MEMORY_POLICY_LIST_FIELDS` if the list card should surface it again.

## TODO: switch the Memory Policy form to tabs

Filed here rather than in the base UI PR because it only earns its cost once
this feature lands. The base form (~14 fields across 5 cards: Policy,
Capture, Retrieval, Write Permissions, Knowledge Projection, Lifecycle) reads
fine as a single scroll — it's smaller than `KnowledgeSourceFormPage`, which
gets by on 2 tabs. But once Capture grows a learning-agent picker, an
extraction schedule, and (likely) an extraction-prompt editor, it stops being
a section and becomes a surface of its own.

Proposed end state, to implement **alongside** the capture-delegation PR
(not before it — restructuring the form twice is wasted motion):

- **Policy** — name, enabled, agent, scope
- **Capture** — capture mode, learning agent, approval/default status,
  allowed record types, (new) extraction schedule/prompt
- **Retrieval** — inject mode, max records, token budget
- **Guardrails** — write permissions (rename from "Write Permissions"),
  knowledge projection, TTL

Reuse the existing tab-with-validation pattern from
`KnowledgeSourceFormPage.tsx` (`tabConfig` / `tabFieldMapping` /
`createFormSubmitHandler`) rather than inventing a new one.
