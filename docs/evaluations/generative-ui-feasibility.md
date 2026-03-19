# Generative UI Feasibility Evaluation for Huf

> **Date**: 2026-03-19
> **Status**: Evaluation complete
> **Verdict**: Directly feasible in current chat — Huf already has ~80% of the infrastructure

---

## 1. Purpose

This document evaluates whether **Tambo-style generative UI** — a pattern where AI dynamically chooses and renders React components inside chat — can be implemented within the Huf codebase.

The evaluation covers:
- Whether Huf's current chat architecture can support AI-selected component rendering
- The cleanest integration path
- Risks and challenges
- A concrete minimal implementation example

**Key finding**: Huf already possesses most of the required infrastructure. The existing `<jsx-preview>` / `<artifact type="jsx">` system with `react-jsx-parser` and a 100+ component registry is functionally a generative UI system. The gap is not architectural — it is in how the AI selects components and how structured the response format is.

---

## 2. Huf Frontend Overview

### Tech Stack
- **React 18.3** with TypeScript strict mode
- **Vite 5.4** build tool
- **React Router v7** under `/huf` basename
- **Tailwind CSS 3.4** with CSS variable theming
- **Radix UI / shadcn/ui** — 54 primitive components
- **Recharts** — full charting library
- **react-jsx-parser** — runtime JSX string → React element rendering
- **Vercel AI SDK** (types only for `ToolUIPart`)
- **Streamdown** for markdown rendering with Shiki code highlighting

### Relevant Architecture Layers

| Layer | Location | Role |
|-------|----------|------|
| API Services | `src/services/chatApi.ts`, `streamChatApi.ts` | REST + SSE communication |
| Message Types | `src/components/chat/types.ts` | `MessageType` with versions, tools, kind |
| Message Mappers | `src/components/chat/chatMessageList.mappers.ts` | API → UI type transformation |
| Message Renderer | `src/components/chat/ChatMessage.tsx` | Per-message rendering dispatch |
| Content Parser | `src/components/chat/MessageContentWithArtifacts.tsx` | Extracts structured tags from text |
| Artifact System | `src/utils/artifactParser.ts`, `jsxPreviewParser.ts` | Regex-based tag extraction |
| JSX Runtime | `src/components/ui/jsx-preview.tsx` | Component registry + react-jsx-parser |
| Rich Renderers | `ArtifactRenderer.tsx`, `JSXPreviewRenderer.tsx` | Type-switched rendering |

---

## 3. Huf Chat Architecture Overview

### Data Flow

```
User Input
  ↓
ChatInput.handleSubmit()
  ↓
streamChatApi.sendMessage()  ──→  POST /huf/stream/<agent>
  │                                     │
  │  onDelta(text) ←── SSE chunks ──────┘
  │       │
  │  setMessages(prev => update versions[0].content)
  ↓
ChatMessageList
  ↓
ChatMessage (per message)
  ↓
MessageContentWithArtifacts
  ├── hasJSXPreviews()?  → parseJSXPreviews() → JSXPreviewRenderer
  ├── hasWebPreviews()?  → parseWebPreviews() → WebPreviewRenderer
  ├── hasArtifacts()?    → parseArtifacts()    → ArtifactRenderer
  └── plain text         → MessageResponse (Streamdown markdown)
```

### Message Model

```typescript
type MessageType = {
  key: string;
  from: 'user' | 'assistant';
  versions: { id: string; content: string }[];
  kind?: string;               // 'Image', 'Tool Result', etc.
  generatedImage?: string;
  generatedAudio?: string;
  voiceMessage?: string;
  tools?: ToolCallInfo[];
};
```

Messages carry content as a **string** in `versions[0].content`. The content is parsed at render time by `MessageContentWithArtifacts` to extract structured blocks.

### Current Rich Content Support

Huf **already supports** rendering AI-generated React components in chat via two mechanisms:

#### Mechanism 1: `<jsx-preview>` tags
The AI emits raw JSX inside `<jsx-preview>` tags in its text response. The parser extracts them, and `JSXPreviewRenderer` renders them using `react-jsx-parser` with a component registry.

#### Mechanism 2: `<artifact type="jsx|chart">` tags
Similar to JSX preview, but wrapped in an artifact container with copy/download/fullscreen actions.

#### The Component Registry (already exists)

`frontend/src/components/ui/jsx-preview.tsx` defines `availableComponents` — a map of **100+ components** the AI can use in JSX strings:

| Category | Components |
|----------|------------|
| **Recharts** | LineChart, BarChart, PieChart, AreaChart, ScatterChart, RadarChart, ComposedChart, Treemap, FunnelChart + axes, grids, tooltips, legends |
| **shadcn/ui** | Card, Table, Badge, Alert, Progress, Tabs, Accordion, Avatar, Skeleton, Button, Separator |
| **Lucide Icons** | 60+ icons (CheckCircle, TrendingUp, DollarSign, Database, etc.) |
| **Built-in Bindings** | `formatNumber`, `formatCurrency`, `formatPercent`, `formatDate`, `sum`, `avg`, `groupBy`, `sortBy`, `COLORS` |

#### Streaming Support

- SSE via `streamAgentResponse()` yields `delta` chunks with `full_response`
- `onDelta` callback updates `versions[0].content` in real time
- `MessageContentWithArtifacts` re-parses on every render, so structured tags are rendered as they complete
- JSXPreview supports `isStreaming` mode with auto-completion of unclosed tags

### Extensibility Points

1. **New parsers**: Add a `has*()` + `parse*()` function, wire into `MessageContentWithArtifacts`
2. **New artifact types**: Add to `ArtifactType` union, add case in `ArtifactRenderer.renderContent()`
3. **New components in registry**: Add to `availableComponents` in `jsx-preview.tsx`
4. **New message kinds**: Add `kind` values, handle in `ChatMessage.tsx` rendering logic
5. **New socket events**: Extend `NewAgentMessageEvent`, update mappers

---

## 4. What Generative UI / Tambo-Style Rendering Means in This Context

The Tambo pattern has these core primitives:

| Tambo Primitive | How Huf Already Implements It |
|-----------------|-------------------------------|
| **Component Registry** | `availableComponents` in `jsx-preview.tsx` — 100+ components mapped by name |
| **AI selects component** | AI includes `<jsx-preview>` or `<artifact type="jsx">` tags with JSX using registered component names |
| **AI supplies props/data** | Props are embedded in the JSX string (`<BarChart data={[...]}><Bar dataKey="value" />`) |
| **Frontend renders component** | `react-jsx-parser` parses JSX string and renders with registered components |
| **Streaming** | `isStreaming` mode + `autoCompleteJsx()` for partial JSX |
| **Fallback** | If JSX parsing fails, `JSXPreviewError` shows error; surrounding text still renders via Streamdown |

**What Huf already does IS generative UI** — the AI generates JSX strings that are rendered as live React components. The key differences from a Tambo-style system are:

1. **Selection granularity**: Tambo uses structured tool calls to select components; Huf uses inline JSX strings in text content
2. **Schema enforcement**: Tambo validates props via Zod schemas; Huf relies on `react-jsx-parser` tolerating malformed JSX
3. **Separation of data and presentation**: Tambo separates component name + props as structured data; Huf bundles everything in a JSX string
4. **Streaming fidelity**: Tambo streams individual prop values via JSON Patch; Huf streams the entire text including JSX

---

## 5. Feasibility Assessment

### Verdict: **Directly feasible in current chat with minimal changes**

Huf's chat architecture already supports AI-rendered React components. The question is not "can it be done" but "how can it be done better."

Three integration tiers are possible, each building on the last:

| Tier | Description | Effort | Changes |
|------|-------------|--------|---------|
| **Tier 0** (already works) | AI emits `<jsx-preview>` with Recharts/shadcn JSX | None | Agent instructions only |
| **Tier 1** (recommended first step) | Add a `<ui-component>` structured tag with type + JSON data, add purpose-built renderers | Small | New parser + 3-5 renderer components + registry |
| **Tier 2** (full generative UI) | Structured response format via tool calls, component state, interactivity | Moderate | Backend changes + new message kind + state management |

**A separate POC is NOT needed.** The existing chat infrastructure is the right place to build this.

---

## 6. Integration Options

### Option A: Leverage the Existing `<jsx-preview>` System (Tier 0)

**Zero code changes required.** Simply instruct the AI agent to emit `<jsx-preview>` tags with JSX that uses the registered components.

Example agent instruction:
```
When presenting data, use <jsx-preview> tags with React components.
Available: Card, CardHeader, CardTitle, CardContent, Table, TableHeader, TableBody, TableRow, TableHead, TableCell, BarChart, Bar, LineChart, Line, PieChart, Pie, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, Badge, Alert, Progress.
Available bindings: formatNumber, formatCurrency, formatPercent, COLORS.
```

**Pros**: Works today, no code changes
**Cons**: JSX strings are fragile, no data/presentation separation, no schema validation, large prompt overhead

### Option B: Structured Component Tag System (Tier 1) — Recommended

Add a new `<ui-component>` tag format where the AI emits a component type and JSON props, and purpose-built renderer components handle the rendering.

```xml
Here are this month's sales figures:

<ui-component type="stats-card" data='{"title":"Revenue","value":48250,"change":12.5,"format":"currency"}' />

<ui-component type="bar-chart" data='{"title":"Monthly Sales","items":[{"month":"Jan","sales":4000},{"month":"Feb","sales":5200}],"dataKey":"sales","categoryKey":"month"}' />

<ui-component type="data-table" data='{"title":"Top Products","columns":["Product","Units","Revenue"],"rows":[["Widget A",142,"$28,400"],["Widget B",98,"$19,600"]]}' />
```

**Architecture**:

```
MessageContentWithArtifacts
  ├── hasUIComponents()?  → parseUIComponents() → UIComponentRenderer
  │     ├── StatsCardRenderer
  │     ├── BarChartRenderer
  │     ├── DataTableRenderer
  │     ├── InfoCardRenderer
  │     └── ... (registry pattern)
  ├── (existing parsers continue to work)
  └── plain text → MessageResponse
```

**What this adds**:
1. A new parser (`uiComponentParser.ts`) — ~50 lines
2. A component registry map (`ui-component-registry.ts`) — type → renderer
3. Purpose-built renderer components that accept typed JSON data — much more reliable than JSX string parsing
4. Graceful fallback — if type is unknown, render the data as a formatted JSON code block

**Pros**:
- Clean data/presentation separation
- Typed props, validatable
- Works alongside existing `<jsx-preview>` (not a replacement)
- Small surface area of change
- Reliable rendering — no JSX string parsing fragility
- Easy to add new component types
- Better prompt efficiency — JSON data is more compact than full JSX

**Cons**:
- Adds a new tag format (but follows the existing pattern)
- Components must be pre-built (but this is actually a feature — it's controlled and safe)

### Option C: Tool-Call-Based Component Selection (Tier 2)

Use the existing tool call system to let the AI "call" a rendering tool that returns structured component data.

```python
# Backend: new tool type
{
    "tool_name": "render_ui",
    "description": "Render a UI component in the chat",
    "parameters": [
        {"name": "component", "type": "string", "description": "Component type"},
        {"name": "data", "type": "object", "description": "Component data"},
    ]
}
```

The tool call result would be stored as a message with special `kind`, and the frontend would render it as a component.

**Pros**: Most "Tambo-like", structured by nature, works with existing tool infrastructure
**Cons**: Requires backend changes, tool calls are visible as separate UI elements, more complex flow

---

## 7. Challenges and Risks

### 7.1 JSX String Fragility (existing system)
Current `<jsx-preview>` relies on the LLM generating valid JSX. Malformed JSX fails silently or shows an error. The structured tag approach (Option B) mitigates this by using JSON data with purpose-built renderers.

### 7.2 Streaming Complexity
JSX preview tags may be split across SSE chunks. The existing `autoCompleteJsx()` handles this for streaming, but a new structured tag system needs its own streaming strategy:
- JSON inside `<ui-component>` tags must be complete before rendering
- During streaming, show a skeleton/placeholder until the closing tag arrives
- The existing parser pattern (regex on full content) already handles this — partial tags simply won't match until complete

### 7.3 Security: Arbitrary Component Rendering
The `react-jsx-parser` system has inherent risk — the AI could potentially emit JSX that accesses window/document via bindings. Mitigations:
- `allowUnknownElements={false}` is already set (only registered components render)
- Bindings are explicitly whitelisted (`Math`, `JSON`, `formatNumber`, etc.)
- The structured approach (Option B) is inherently safer — data is JSON, rendering is controlled

### 7.4 Schema Consistency
If the AI emits `<ui-component type="bar-chart">` with incorrect data shape, the renderer needs to handle it gracefully. Each renderer should validate its data and show a fallback.

### 7.5 Backend Response Format
No backend changes are needed for Options A or B. The AI simply includes structured tags in its text response. The backend already stores and transmits arbitrary text content.

### 7.6 UX Consistency
Rich components must visually integrate with the chat. They should:
- Use the same Tailwind CSS variable theming as the rest of the app
- Respect dark mode (via class-based toggling)
- Be responsive within the chat message width
- Not break the chat scroll behavior

### 7.7 Maintainability
Adding new component types should be easy. The registry pattern ensures:
- One file per renderer component
- One entry in the registry map
- No changes to the core parsing/rendering pipeline

---

## 8. Opportunities and Benefits

### 8.1 Richer AI UX
Instead of "Revenue increased 12.5% to $48,250", the user sees a stats card with trend indicator, formatted currency, and visual emphasis.

### 8.2 Charts and Tables in Chat
Already supported via `<jsx-preview>`, but the structured approach makes this more reliable and maintainable.

### 8.3 Task-Oriented UI
Components like approval cards, form summaries, and action buttons can make the chat more actionable.

### 8.4 Better Structured AI Responses
Separating data (JSON) from presentation (pre-built components) means:
- Smaller prompts (no full JSX instructions needed)
- More reliable rendering
- Reusable data for export/analysis

### 8.5 Progressive Enhancement
The system degrades gracefully:
- If a component type is unknown → render as formatted JSON
- If JSON is malformed → show the raw content
- If the tag is incomplete during streaming → wait until complete
- Surrounding text always renders normally via markdown

---

## 9. Recommended Path

### Recommendation: **Option B (Tier 1) — Structured Component Tag System**

This is the cleanest integration because it:
1. Follows the existing architectural pattern (tag parser + renderer, exactly like artifacts and JSX previews)
2. Requires no backend changes
3. Adds controlled, purpose-built components instead of relying on arbitrary JSX strings
4. Is safer (JSON data, not executable JSX)
5. Is a small, incremental addition (~200-300 lines of new code)
6. Preserves all existing functionality
7. Does not require a separate POC — it slots directly into the chat

### Implementation Phases

| Phase | Work | Scope |
|-------|------|-------|
| **1. Parser** | Create `uiComponentParser.ts` with `hasUIComponents()` and `parseUIComponents()` | 1 file, ~60 lines |
| **2. Type definitions** | Add `ParsedUIComponent` type to `artifact.types.ts`, create `UIComponentType` union | ~20 lines |
| **3. Registry** | Create `ui-component-registry.ts` mapping type strings to React components | 1 file, ~30 lines |
| **4. First renderers** | Build `StatsCard`, `SimpleBarChart`, `DataTable` renderers | 3 files, ~80 lines each |
| **5. Wire into pipeline** | Add `UIComponentRenderer` and integrate into `MessageContentWithArtifacts` | ~30 lines of changes |
| **6. Fallback** | Add `UnknownComponentFallback` for graceful degradation | 1 file, ~30 lines |
| **7. Agent instructions** | Document available component types and data schemas for agent prompts | Documentation only |

---

## 10. Minimal Implementation Example

Below is a concrete, minimal example showing how a `StatsCard` component would work end-to-end in Huf's current architecture.

### 10.1 AI Response Format

The AI agent would emit this in its text response:

```
Based on your sales data, here's a summary:

<ui-component type="stats-card" data='{"title":"Total Revenue","value":48250,"change":12.5,"changeLabel":"vs last month","format":"currency"}' />

<ui-component type="bar-chart" data='{"title":"Monthly Sales","items":[{"name":"Jan","value":4000},{"name":"Feb","value":5200},{"name":"Mar","value":4800}],"dataKey":"value","categoryKey":"name"}' />

Revenue is trending upward, with February showing the strongest performance.
```

### 10.2 Parser — `uiComponentParser.ts`

```typescript
import type { ParsedUIComponent, UIComponentParseResult } from '@/types/artifact.types';

const UI_COMPONENT_REGEX =
  /<ui-component\s+type=["']([^"']+)["']\s+data=["']([^"']+)["']\s*\/>/gi;

export function parseUIComponents(content: string): UIComponentParseResult {
  const components: ParsedUIComponent[] = [];
  UI_COMPONENT_REGEX.lastIndex = 0;

  const text = content.replace(UI_COMPONENT_REGEX, (_match, type, rawData) => {
    try {
      const data = JSON.parse(rawData.replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
      components.push({ type, data });
    } catch {
      components.push({ type, data: null, error: 'Invalid JSON data' });
    }
    return '';
  });

  const cleanedText = text.replace(/\n{3,}/g, '\n\n').trim();
  return { text: cleanedText, components };
}

export function hasUIComponents(content: string): boolean {
  if (!content) return false;
  UI_COMPONENT_REGEX.lastIndex = 0;
  return UI_COMPONENT_REGEX.test(content);
}
```

### 10.3 Type Definitions

Add to `artifact.types.ts`:

```typescript
export interface ParsedUIComponent {
  type: string;
  data: Record<string, unknown> | null;
  error?: string;
}

export interface UIComponentParseResult {
  text: string;
  components: ParsedUIComponent[];
}
```

### 10.4 Component Registry — `ui-component-registry.ts`

```typescript
import type { ComponentType } from 'react';
import type { ParsedUIComponent } from '@/types/artifact.types';
import { StatsCardRenderer } from './renderers/StatsCardRenderer';
import { SimpleBarChartRenderer } from './renderers/SimpleBarChartRenderer';
import { DataTableRenderer } from './renderers/DataTableRenderer';

export interface UIComponentRendererProps {
  component: ParsedUIComponent;
}

const registry: Record<string, ComponentType<UIComponentRendererProps>> = {
  'stats-card': StatsCardRenderer,
  'bar-chart': SimpleBarChartRenderer,
  'data-table': DataTableRenderer,
};

export function getUIComponentRenderer(type: string) {
  return registry[type] ?? null;
}

export function getRegisteredTypes(): string[] {
  return Object.keys(registry);
}
```

### 10.5 Sample Renderer — `StatsCardRenderer.tsx`

```typescript
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UIComponentRendererProps } from '../ui-component-registry';

interface StatsCardData {
  title: string;
  value: number;
  change?: number;
  changeLabel?: string;
  format?: 'number' | 'currency' | 'percent';
}

function formatValue(value: number, format?: string): string {
  switch (format) {
    case 'currency':
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
    case 'percent':
      return `${value.toFixed(1)}%`;
    default:
      return new Intl.NumberFormat().format(value);
  }
}

export function StatsCardRenderer({ component }: UIComponentRendererProps) {
  const data = component.data as StatsCardData | null;
  if (!data || !data.title) {
    return <div className="text-sm text-muted-foreground">Invalid stats card data</div>;
  }

  const isPositive = (data.change ?? 0) >= 0;

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {data.title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{formatValue(data.value, data.format)}</div>
        {data.change !== undefined && (
          <div className={cn('mt-1 flex items-center gap-1 text-xs',
            isPositive ? 'text-green-600' : 'text-red-600'
          )}>
            {isPositive ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
            <span>{isPositive ? '+' : ''}{data.change.toFixed(1)}%</span>
            {data.changeLabel && <span className="text-muted-foreground">{data.changeLabel}</span>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

### 10.6 Integration Point — `MessageContentWithArtifacts.tsx`

Add the new parser alongside existing parsers:

```typescript
import { parseUIComponents, hasUIComponents } from '@/utils/uiComponentParser';
import { UIComponentRenderer } from './UIComponentRenderer';

// Inside the function:
const contentHasUIComponents = hasUIComponents(decodedContent);

// After existing parsing:
if (contentHasUIComponents) {
  const parsed = parseUIComponents(textContent);
  textContent = parsed.text;
  uiComponents = parsed.components;
}

// In JSX return:
{uiComponents.map((comp, idx) => (
  <UIComponentRenderer key={`${messageKey}-ui-${idx}`} component={comp} />
))}
```

### 10.7 How It Works with Streaming

During SSE streaming:
1. Text arrives chunk by chunk in `versions[0].content`
2. `MessageContentWithArtifacts` re-renders on each update
3. Partial `<ui-component` tags won't match the regex → surrounding text renders normally
4. Once the full tag arrives (self-closing `/>`), the regex matches and the component renders
5. The transition is seamless — text appears first, then the component materializes

No special streaming handling is needed because:
- The tags are self-closing (`/>`) — no unclosed-tag problem
- The regex is greedy on attribute values — partial JSON in `data='...'` won't match until the closing quote
- This is the same behavior as existing `<web-preview>` tags

---

## 11. File and Code References

### Files Examined — Chat System

| File | Why It Matters |
|------|----------------|
| `frontend/src/components/chat/ChatMessage.tsx` | Per-message rendering dispatch — handles tools, images, audio, and content |
| `frontend/src/components/chat/ChatInput.tsx` | Message submission, streaming integration, `onDelta` wiring |
| `frontend/src/components/chat/MessageContentWithArtifacts.tsx` | **Central parsing/rendering hub** — where new component types plug in |
| `frontend/src/components/chat/chatMessageList.mappers.ts` | API → UI message transformation, socket event handling |
| `frontend/src/components/chat/types.ts` | `MessageType` definition — the UI message shape |
| `frontend/src/components/chat/ArtifactRenderer.tsx` | Type-switched artifact rendering (code, html, svg, mermaid, jsx, chart) |
| `frontend/src/components/chat/JSXPreviewRenderer.tsx` | Standalone JSX preview rendering |

### Files Examined — Rich Content System

| File | Why It Matters |
|------|----------------|
| `frontend/src/components/ui/jsx-preview.tsx` | **Component registry** — 100+ components + bindings + react-jsx-parser integration |
| `frontend/src/utils/artifactParser.ts` | Tag extraction pattern — regex-based, serves as template for new parsers |
| `frontend/src/utils/jsxPreviewParser.ts` | JSX preview extraction with code fence unwrapping |
| `frontend/src/utils/webPreviewParser.ts` | Web preview extraction — simplest parser, good reference |
| `frontend/src/types/artifact.types.ts` | Type definitions for parsed artifacts, web previews, JSX previews |

### Files Examined — API and Services

| File | Why It Matters |
|------|----------------|
| `frontend/src/services/chatApi.ts` | REST API for conversations/messages, response shapes |
| `frontend/src/services/streamChatApi.ts` | SSE streaming, `StreamChunk` types, `sendMessage` unified API |

### Files Examined — AI Elements

| File | Why It Matters |
|------|----------------|
| `frontend/src/components/ai-elements/message.tsx` | `MessageResponse` wrapping Streamdown for markdown |
| `frontend/src/components/ai-elements/tool.tsx` | Tool call rendering pattern — compound component |
| `frontend/src/components/ai-elements/artifact.tsx` | Artifact container — compound component pattern |

---

## 12. External References Reviewed

### Tambo AI
- **Concept**: Component registry with Zod schemas, AI selects components and generates props, frontend renders
- **Architecture**: Two-stage streaming (JSON Patch for props), component state management, interactable components
- **Relevance to Huf**: The core loop (register components → AI selects → render) already exists in Huf via `jsx-preview`. Tambo's contribution is the structured selection (tool calls vs inline tags) and typed schemas (Zod vs implicit JSX)
- **Transferable patterns**: Component registry concept (already exists), graceful fallback (partially exists), data/presentation separation (the key improvement opportunity)
- **Non-transferable patterns**: Remote state management (Tambo Cloud), NestJS backend (Huf uses Frappe), Zod-at-registration (Huf doesn't use Zod for component props)

### Vercel AI SDK Generative UI
- **Concept**: Server components streamed to client, `streamUI` with tool-based component selection
- **Relevance**: Huf uses Vercel AI SDK types (`ToolUIPart`) but not the RSC streaming
- **Non-transferable**: Requires Next.js RSC, tight framework coupling, currently paused/experimental

### LangChain / json-render
- **Concept**: AI generates JSON spec describing component tree, client renders
- **Relevance**: Closest to the recommended Option B — structured data with client-side rendering
- **Transferable**: JSON-based component specification, type-safe registry, framework-agnostic rendering

---

## 13. Conclusion

### Can Huf chat support AI-rendered React components?
**Yes, it already does.** The `<jsx-preview>` system with `react-jsx-parser` and a 100+ component registry is a functioning generative UI system.

### What is the cleanest way to improve it?
**Add a structured `<ui-component>` tag system** (Option B) alongside the existing JSX preview system. This provides:
- Reliable, typed rendering via purpose-built components
- Clean data/presentation separation
- Minimal code changes (~200-300 lines)
- No backend changes needed
- Graceful fallback

### What is the smallest realistic implementation we can test?
A `StatsCard` renderer: one parser (~60 lines), one type definition (~10 lines), one registry (~30 lines), one renderer component (~50 lines), and ~15 lines of changes to `MessageContentWithArtifacts`. Total: ~165 lines of new/changed code.

### Should we do it in existing chat or as a separate POC?
**In existing chat.** The architecture is already there. Building a separate POC would duplicate infrastructure that already exists and works well. The structured tag approach plugs directly into the existing parsing pipeline with zero risk to current functionality.

---

## Appendix A: Comparison of Approaches

| Aspect | Tier 0 (JSX Preview) | Tier 1 (Structured Tags) | Tier 2 (Tool Calls) |
|--------|---------------------|-------------------------|---------------------|
| Backend changes | None | None | Moderate |
| Frontend changes | None | Small (~300 LOC) | Moderate (~600 LOC) |
| Rendering reliability | Medium (JSX string parsing) | High (typed JSON + built components) | High |
| AI prompt complexity | High (full JSX instructions) | Low (type + JSON schema) | Low |
| Streaming support | Yes (autoCompleteJsx) | Yes (tag completion) | Requires new flow |
| Safety | Medium (allowUnknownElements=false) | High (controlled renderers) | High |
| Extensibility | Add to availableComponents | Add registry entry + renderer | Add tool + handler + renderer |
| UX polish | Variable (AI-generated layout) | Consistent (designed components) | Consistent |

## Appendix B: Recommended Component Types for Initial Implementation

| Type | Description | Data Shape |
|------|-------------|------------|
| `stats-card` | Single metric with trend | `{title, value, change, format}` |
| `bar-chart` | Simple bar chart | `{title, items[], dataKey, categoryKey}` |
| `line-chart` | Simple line chart | `{title, items[], lines[], xKey}` |
| `pie-chart` | Simple pie chart | `{title, items[], nameKey, valueKey}` |
| `data-table` | Basic data table | `{title, columns[], rows[][]}` |
| `info-card` | Rich information card | `{title, description, items[], icon}` |
| `progress-card` | Progress/completion card | `{title, value, max, label}` |
| `key-value-list` | Key-value pairs display | `{title, items[{key, value}]}` |
