# DataInput: the one input for a value in a flow step (UX-9)

`components/flow/data/DataInput.tsx`. Typed text and data from earlier steps live in one box. Nobody chooses a "mode": what is stored is worked out from what is on screen. (The old `FlowValueInput` wrapper is gone: every step form uses `DataInput`, directly or through `ValueField` in `components/flow/forms/fields.tsx`.)

```tsx
import { DataInput } from '@/components/flow/data/DataInput';

<DataInput
  nodeId={nodeId}              // the step this field belongs to; without it there is no "+ Use data"
  value={cfg.subject}          // any stored Value: text, {$from}, {$template, vars}, number, list, object
  onChange={(v) => patch({ subject: v })}
  kind="text"                  // text | longtext | number | url | json | yesno
  label="Subject"              // optional: renders the label (and "(optional)" with `optional`)
  placeholder="Order received"
  hint="The subject line of the email."
  testId={f('subject')}        // the box; "<testId>-picker" is the "+ Use data" button, "<testId>-preview" the preview line
/>
```

| kind | box | stored |
|---|---|---|
| `text` | one line, chips and text | string, `{$from}` (the whole value is one chip) or `{$template, vars}` |
| `longtext` | taller box, Enter makes a new line | same |
| `url` | one line, URL keyboard; `/` only opens the picker at the start of a word | same |
| `number` | one line; text that is only a number is stored as a number, other text shows "Enter a number" | number, `{$from}` or template |
| `json` | the JSON area titled "Advanced (JSON)" (Format, Copy, live error) | the parsed list/object; half-typed JSON is kept as text |
| `yesno` | Yes / No / Not set choice | `true`, `false` or absent |

Extra props: `id`, `label`, `optional`, `disabled`, and `accept`: `"list"` for a field that takes a whole list (a loop's items, a transform's rows): the picker then shows lists only and a pick sets `{$from: <list>}` directly; `"one"` for a field that takes exactly one thing from an earlier step (a loop's "result to collect"). Both are pick-only (typing does nothing, because a reference is stored). `scope="loop-body"` lists the steps inside the loop.

A value that is a list or an object (an old flow, or JSON typed before) opens as "Advanced (JSON)" automatically; "Use plain text instead" turns it back into text.

## What the person sees
- "+ Use data" in the box's right edge, or type `/` at the start of a word. The picker opens BESIDE the box (left of the step panel; above it on a phone), never over it.
- Level 1: steps by icon and title, "Trigger: Webhook" first, then the closest step. A search box on top searches every field by name or example.
- Level 2: the step's fields by name with a real example ("Customer > Name  Ada Lovelace"). Nothing has run yet: "No sample yet: run a test", with "Use last real request" for a webhook and "Use last real message" for a chat trigger (WhatsApp, Telegram). The chat one asks `samples_api.get_last_gateway_message`, not the webhook endpoint; numbers are masked and ids never listed. Without a real message the registry's sample is used.
- A list: Each item (use in a loop) / First item / All items, joined with commas / How many items. Something with parts: "Show as summary table".
- Each pick is a chip "Customer > Name . New order" at the caret; the example shows on hover. Click a chip to change its field, `x` or Backspace removes it, a deleted step shows a red "Missing: step deleted".
- Under the box: "What this will become: Hi Ada Lovelace", from examples; unknown parts read `[Customer name: no sample yet]`. Never JSON.
- Keyboard: `/` opens, arrows move, Enter inserts (Right opens a level, Left goes back), Esc closes (and types the `/` if nothing was picked).

## Stored forms (lossless, `lib/flow-data/chips.ts`)
| on screen | stored |
|---|---|
| `Order {42}` typed | `"Order {42}"` (plain text, braces are just braces) |
| one chip | `{"$from": "n1.customer.name"}` |
| `Hi [Name], total [Total]` | `{"$template": "Hi {name}, total {total}", "vars": {"name": {"$from": ...}, "total": {"$from": ...}}}` |
| typed `{` or `}` next to a chip | `{{` / `}}` in the template |
| a whole object / list as text | variable name prefix the engine reads (`graph/templates.py`): `table_x` (rows "Label: value", one per line), `joined_x` (items with commas), `count_x` (how many) |

`serializeValue(parseValue(v))` deep-equals `v` for every form above, including a template without `vars`, variables the text never mentions, a variable that is not a plain reference, and `{name}` with no variable. A bare `input` or `trigger` is never inserted: the picker only offers fields (or "Its result" for a step as a whole).

## Migrating a form (UX-12)
1. Replace `<FlowValueInput ...>` with `<DataInput ... />` (same props, plus `kind`; keep `testId`, so the box, `-picker`, `-preview` ids stay).
2. A field that holds a list or a set of named values: `kind="json"`. A list from an earlier step: `accept="list"`. A number: `kind="number"`. Yes/No: `kind="yesno"`.
3. Remove hint text that talks about modes, `$from`, `{name}` or "Choose JSON as the value type".
4. A field whose stored form is a plain string with placeholders, not a `Value` (the approval message and title, the router's question, the End outcome label: `{input.customer.name}`; also `{table:x}`, `{joined:x}`, `{count:x}`), is edited with the same chip box through `lib/flow-data/textRefs.ts` (`toTextRefs` / `fromTextRefs`). The agent's prompt, stored as `prompt` plus `prompt_bindings`, goes through `promptToValue` / `valueToPrompt`. `forms/useAsValue.ts` keeps the box from redrawing while typing. The server fills the placeholders in with `render_text_refs`, which understands the three wordings (`huf/ai/flow/support/router_text.py`).
5. Journeys: `type` works on the box (`fill`); `expect value` / `value_matches` read its words (chips as "Customer > Name . New order"); to put data in, click `<testId>-picker`, then `flow-use-data-type-it`, type `input.customer.name` in `flow-use-data-typed`, press Enter. `fix/ux9/update_old_journeys.py` shows the rewrite.

## Server
`huf.ai.flow.catalog.api.get_data_catalog(flow_id, node_id)` (editors of the flow only) returns the steps before `node_id` (steps on every path from the trigger) with their fields and examples: the example saved on the step (`_sample`), else the latest successful run, else the last webhook request, else, for a data trigger, the document type's fields (labels from the DocType, one recent record you may read, and "Customer > Credit limit" for Link fields, filled in by `triggers.build_doc_event_payload` as `input._links.<field>.<field>`). Keys that cannot be written as a reference are returned as `advanced_only` with no path. The editor builds the same list from the steps on screen, so a step added a moment ago is there; the server adds the examples.
