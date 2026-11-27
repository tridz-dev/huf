# Flow builder embed mode: contract

Status: design (H-W7-01), awaiting coordinator review. Nothing described here is built yet. H-W7-02 to H-W7-06 implement it.

Embed mode lets an installed app (the "host", first consumer: Happiol) show the Huf flow builder for one flow inside its own screen, with a reduced step palette and the host's colours.

## 1. What exists today

| Piece | Behaviour that matters here |
|---|---|
| `huf/hooks.py` `website_route_rules` | `/huf/<path>` renders the single page `huf`. |
| `huf/www/huf.py` | `get_context` puts the CSRF token and boot data into the built shell `huf/www/huf.html` (copied from the Vite build by `frontend/scripts/copy-html-entry.mjs`). `no_cache = 1`. Guests get the shell too. |
| `frontend/src/App.tsx` | Router basename `/huf`. The canvas is `/flows/:flowId`, inside `UnifiedLayout` (app chrome); a global `CommandPalette` and `Toaster` are mounted beside the routes. |
| `frontend/src/pages/FlowCanvasPage.tsx` | The canvas and step panel; takes `flowId` from the route and sends the user to `/flows` without one. |
| `frontend/src/lib/sessionInvalidation.ts` | On a lost session, sets `window.location` to `/login`. |
| `huf.ai.flow.api.get_node_schemas` | Field definitions of built-in step types. |
| `huf.ai.flow.catalog.api.list_node_types` | Only the app step types from the `huf_flow_nodes` hook; each has an `app` field. |
| `frontend/src/lib/personalization.ts`, `index.css` | Light is `:root`; dark is `data-theme="midnight"` on the root element. The user's choice is in `localStorage`. |
| Frappe session cookie | `SameSite=Lax`. |

No service worker is registered (`frontend/src/pwa/registerSW.ts` removes old ones), so a cached shell cannot bypass response headers on current builds.

## 2. Decisions

| Topic | Decision | Reason |
|---|---|---|
| Container | An **iframe**. The `<huf-flow-builder>` custom element (H-W7-05) is only a wrapper that creates the iframe and relays messages. | The builder owns a router, global CSS, portals, toasts and `window` listeners. Mounting it as a web component in the host DOM would leak styles and events both ways. |
| Auth | The **existing Frappe session cookie**. No embed token, no credential in the URL or in a message. | Host and Huf are apps on one Frappe site. API calls from the frame are ordinary same-origin calls with the CSRF token from boot. |
| Supported hosts | Same origin (normal case) and same site (a sibling subdomain). **Cross-site hosts are not supported.** | A `Lax` cookie is not sent to a cross-site frame. Do not weaken it to `SameSite=None`. |
| Route | `/huf/embed/flow/<flow_id>` | Covered by the existing `/huf/<path:app_path>` rule. |
| Serving | `huf/www/huf.py` detects the `/huf/embed/` path and applies the embed headers and checks. No new route rule or second HTML shell. | The shell is a build artefact; one shell avoids a second copy step. This narrows H-W7-04: `huf_embed.py` and the `hooks.py` edit are not needed. |
| Scope of v1 | Edit, test, save, publish and unpublish **one existing flow**. No flow list, creation, deletion or rename of other flows. | The host owns its list screen and creates flows server-side. |

The iframe is not a security boundary between host and Huf: a same-origin host script can read the frame and call the same APIs as the user. Security comes from server permissions and publish checks. The frame and message rules below stop foreign sites and keep data out of the message channel.

### 2.1 URL

```
/huf/embed/flow/<flow_id>?app=<app_name>[&mode=light|dark][&theme=<base64url JSON>]
```

- `flow_id`: URL-encoded Flow Definition id.
- `app`: required. An installed app's name (`^[a-z][a-z0-9_]*$`). Read once at load; no message can change it.
- `mode`, `theme`: first-paint appearance, see section 5.
- Unknown parameters are ignored. The URL never carries tokens, member keys, names, phone numbers or e-mail addresses.

`<flow_id>` with a `?run=<run_id>` parameter opens that run's trace, as `/flows/<id>?run=` does today.

### 2.2 Frame headers and server checks (H-W7-04)

Site config:

```json
{ "huf_embed_frame_ancestors": ["'self'"] }
```

- Every response for `/huf/embed/...` carries `Content-Security-Policy: frame-ancestors <list>`.
- Key missing, empty, not a list, or with no valid entry: `frame-ancestors 'none'`. A same-origin host therefore needs `'self'` set explicitly.
- Valid entries: `'self'`, or an exact origin `https://host[:port]` (`http://` only when `developer_mode` is on). Entries with `*`, a path, whitespace, `;` or `,` are dropped. This prevents header injection and wildcards.
- Guest, user without the `flows.use` capability, or user without read permission on the flow: HTTP 403, and no boot data for the flow. The header is set **before** the check raises, so the 403 page follows the same policy.
- The server puts `boot.huf_embed = {"allowed_origins": [...]}` into boot data: the same validated list, with `'self'` replaced by the site's own origin. The frontend never derives allowed origins from the URL or `document.referrer`.
- Some bench proxy configs add `X-Frame-Options: SAMEORIGIN`. Browsers that support `frame-ancestors` ignore it when the CSP directive is present; verify this for a same-site subdomain host on a real proxy.
- Non-embed `/huf` responses are unchanged.

### 2.3 Auth and session loss

- Open to the user exactly what `/huf/flows/<id>` would allow. Embed mode grants nothing. Save and publish keep their server checks (`Flow Definition` write, `huf.ai.flow.publish_guard.check_can_publish`, the Flow Definition validator).
- CSRF: the existing token and retry handler.
- In embed mode a lost session must **not** navigate the frame to `/login`. Show the signed-out state and send `error` with code `session_expired`. The host sends the user to sign in at top level, then reloads the frame. This touches `sessionInvalidation.ts`, which H-W7-04 must add to its file scope.

### 2.4 What is removed from the page

- No `UnifiedLayout` sidebar, breadcrumbs, account menu, flows sidebar or global command palette. Keep the canvas, the step panel, run and test views, and a slim toolbar (title, save state, Test, Save, Publish or Unpublish). Flow-scoped shortcuts stay.
- Links that leave the editor (flow list, connections, providers, gateways, saved procedure) must not navigate the frame. Send `navigate` instead (section 4). Links that already open a new tab keep doing so.
- Window title changes are harmless and may stay.

## 3. App-scoped palette (H-W7-02)

Input: the `app` URL parameter, passed as `list_node_types(app=<app_name>)`.

With `app` given, the server returns:

1. that app's `huf_flow_nodes` types (`builtin: false`, full descriptor as today);
2. one entry `{"type": <id>, "builtin": true}` for each built-in type in the embed allow-list below that exists on this version.

The palette shows only these ids; field definitions for built-ins still come from `get_node_schemas`. Without `app` the endpoint behaves as today. An `app` that is not installed raises a validation error, and the frame shows the `unknown_app` state. It never falls back to the full palette.

Built-in allow-list (one constant on the server):

| Included | `trigger.unset`, `trigger.schedule`, `trigger.doc-event`, `condition`, `router.decision`, `transform`, `foreach`, `wait`, `stop`, `output`, `human.approval`, `member.set` |
|---|---|
| Included once they exist | `send.message` (H-W2-03), the split node (H-W2-07), `knowledge.search` (H-W5-02), and later Huf nodes added to the constant on purpose |
| Excluded | `code.run`, `tool.call`, `doc.create`, `doc.get`, `doc.update`, `flow.call`, `agent.run`, `router.llm`, `state.get`, `state.set`, `state.delete`, `trigger.webhook`, `trigger.gateway`, `trigger.whatsapp`, `trigger.telegram`, `parallel`, `validate` |

A new built-in is excluded until added. There is no built-in `ledger_write` step; the generic write paths (`tool.call`, `doc.create`, `doc.update`, `code.run`) are excluded so the embed cannot be used to compose one (G1).

Rules:

- The scope applies to **every** way of adding a step: palette, command search, insert-on-edge, duplicate, paste and "change step type".
- A step already in the flow whose type is out of scope stays on the canvas and in the saved definition, shown read-only with "This step cannot be edited here". Saving must not drop or rewrite it.
- **The palette is not a security control.** The `app` parameter is user-editable and the save API accepts any definition. Forbidding a step for an app's flows is the job of server-side publish checks: the node's own `validate`, the publish guard, and the app's flow-validation hook (H-W2-10).

## 4. postMessage protocol

### 4.1 Envelope and origin rules

```ts
interface HufEmbedMessage<T extends string, P> {
  ns: 'huf.flow.embed';
  v: 1;
  type: T;
  payload: P;
}
```

- Guest accepts a message only if `event.source === window.parent` **and** `event.origin` is in `boot.huf_embed.allowed_origins`.
- Host (mount package) accepts only if `event.source === iframe.contentWindow` **and** `event.origin` equals the origin of the iframe URL it created.
- `targetOrigin` is always an exact origin, never `*`. Before `host.init` the guest posts `guest.ready` once to each allowed origin (the browser drops mismatches); after it, only to the `event.origin` of that `host.init`.
- Wrong `ns`, `v`, unknown `type` or a payload that fails validation: ignore silently. Unknown payload keys are ignored.
- Messages larger than 8 KB are ignored.
- The frame is not framed (`window.parent === window`): no messages are sent or handled.

### 4.2 Messages

Host to guest:

| type | payload | effect |
|---|---|---|
| `host.init` | `{ mode?: 'light'\|'dark', tokens?: Record<string,string> }` | Reply to `guest.ready`; applies appearance. |
| `host.theme` | `{ mode?: 'light'\|'dark', tokens?: Record<string,string> }` | Changes appearance. `tokens` replaces the previous set. |

No host message can save, publish, edit, change the flow or app, or run code. To change flow or app, the host reloads the frame with a new URL.

Guest to host:

| type | payload | when |
|---|---|---|
| `guest.ready` | `{}` | Script is listening. |
| `guest.loaded` | `{ flow_id: string, version: number, status: 'Draft'\|'Active', can_write: boolean }` | Flow is on screen. |
| `guest.dirty` | `{ flow_id: string, dirty: boolean }` | Unsaved state changes. |
| `guest.saved` | `{ flow_id: string, version: number, unfinished: number }` | Save succeeded. `unfinished` is a count only. |
| `guest.publish_state` | `{ flow_id: string, status: 'Draft'\|'Active' }` | Publish or unpublish succeeded. |
| `guest.navigate` | `{ target: 'flow_list'\|'connections'\|'providers'\|'gateways'\|'procedure' }` | The user chose a link that leaves the editor. The host decides what to do. |
| `guest.error` | `{ code: ErrorCode, flow_id?: string }` | A state from section 6, or a failed save or publish. |

```ts
type ErrorCode =
  | 'session_expired' | 'not_permitted' | 'not_found' | 'unknown_app'
  | 'load_failed' | 'save_failed' | 'publish_refused';
```

### 4.3 No PII (G4)

Payloads contain only the fields above: ids, numbers, booleans, fixed enums and (host to guest) appearance values. Never: flow or step names, step settings, definition JSON, samples, trigger payloads, run data, member keys, user names, server error text or tracebacks. Run ids are not sent. The guest builds each payload field by field; it must not spread an API response or an `Error` into a message. Neither side logs message payloads to the console or to the server. Flow ids are chosen by the host and must not contain personal data.

## 5. Theme tokens (H-W7-03)

The host sends names from this closed set; Huf maps each to its own CSS variable. Host variable names and raw CSS are never accepted.

| Token | Huf variable | Value type |
|---|---|---|
| `surface` | `--paper` | colour |
| `surface-sunken` | `--paper-deep` | colour |
| `panel` | `--panel` | colour |
| `text` | `--ink` | colour |
| `text-soft` | `--ink-soft` | colour |
| `text-muted` | `--steel` | colour |
| `border` | `--line` | colour |
| `primary` | `--primary` | colour |
| `primary-text` | `--primary-foreground` | colour |
| `accent` | `--signal` | colour |
| `accent-text` | `--signal-ink` | colour |
| `success` | `--good` | colour |
| `warning` | `--warning` | colour |
| `danger` | `--destructive` | colour |
| `radius` | `--r` | length |
| `radius-sm` | `--r-sm` | length |
| `font-body` | `--body` | font list |
| `font-display` | `--display` | font list |

- colour: `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb()`, `rgba()`, `hsl()`, `hsla()`. The host resolves its own `var(...)` to a computed value before sending.
- length: `0` to `32px`.
- font list: letters, digits, spaces, commas, quotes and hyphens, at most 200 characters. Fonts are not downloaded; only installed or system fonts apply.
- Anything else (including `url(`, `var(`, `;`, `{`) drops that token. Unknown names are ignored. Apply with `element.style.setProperty` on the root element, never by building a stylesheet string.
- `mode` maps to light (no `data-theme`) or dark (`data-theme="midnight"`). In embed mode it must not write the user's `localStorage` preference, and the system-theme listener must not override a mode the host set. Without `mode`, the user's preference applies.
- Without tokens the builder looks exactly like today. The host sends a new token set when it switches light and dark.
- The URL `theme` parameter is base64url of `{"<token>": "<value>"}`, validated by the same function, at most 2 KB.
- The host is responsible for contrast; Huf does not recompute tints from host colours.

## 6. Loading and error states

| State | Guest shows | Message |
|---|---|---|
| Loading | The existing page loader, in the first-paint theme | none, then `guest.loaded` |
| Signed out | "You are signed out." No login form in the frame | `session_expired` |
| No permission | The existing no-access panel, without app chrome | `not_permitted` |
| Flow missing | "This flow was not found." | `not_found` |
| Bad `app` | "This editor is not set up correctly." | `unknown_app` |
| Load failed | Message with a Retry button | `load_failed` |
| Save failed | The editor keeps the changes and shows the error | `save_failed` |
| Publish refused | The existing readable refusal, inside the frame | `publish_refused` |

A server-side 403 (section 2.2) renders no app, so it sends no message. The mount package therefore starts a 20 second timer: without `guest.ready` it replaces the frame with its own "The flow editor could not be loaded" state with Retry, and fires an `error` event with code `load_failed`. A frame blocked by `frame-ancestors` ends in the same state.

Unsaved changes: the guest keeps the browser's `beforeunload` protection if present; the host must also confirm before removing the element while the last `guest.dirty` was `true`.

## 7. Mount package (H-W7-05)

```html
<script type="module" src="/assets/huf/embed/huf-flow-builder.js"></script>
<huf-flow-builder flow="welcome-journey" app="happiol" mode="light" theme='{"accent":"#2563eb"}'></huf-flow-builder>
```

- Attributes: `flow` (required), `app` (required), `src-origin` (default: current origin), `mode`, `theme` (JSON), `run`.
- Changing `flow`, `app`, `src-origin` or `run` reloads the frame. Changing `mode` or `theme` sends `host.theme`.
- DOM events, with the validated payload as `detail`: `ready`, `loaded`, `dirty`, `saved`, `publish-state`, `navigate`, `error`.
- The element fills its parent; the host gives it a height. No auto-resize.
- The bundle has a stable file name and no dependency on React, so hosts can include it directly. It needs its own build entry.

## 8. What the host (Happiol) must provide

| Field | Where | Value |
|---|---|---|
| `huf_embed_frame_ancestors` | site config | `["'self'"]`, plus exact origins only if the host screen is on a same-site subdomain |
| `app` | element attribute | the app's installed name, matching the prefix of its node ids (`happiol.*`, or the pre-rename name until the rename lands) |
| `flow` | element attribute | id of a Flow Definition the app already created |
| `huf_flow_nodes` | app `hooks.py` | the app's step types (existing hook, no new fields) |
| Server-side flow policy | app hook (H-W2-10) | rules that refuse forbidden steps at publish; the palette does not enforce them |
| Roles | app setup | editing users get a Huf role with `flows.use` plus read and write on Flow Definition; publishing sensitive steps still needs `flows.publish_sensitive` |
| `mode`, `theme` | element attributes | values computed from the host's global tokens, updated on theme change |
| `navigate` handler | host script | where flow list and connection links go |
| `error` handler | host script | sign-in redirect on `session_expired` (top-level window) |
| Container | host page | an element with an explicit height; an unsaved-changes confirm |

## 9. Security checklist

- [ ] `frame-ancestors` on every embed response, including 403; default `'none'`.
- [ ] Config entries validated; no wildcard, no injection into the header.
- [ ] No token, secret or PII in URL, attributes, messages or logs.
- [ ] Session cookie attributes unchanged; no `ignore_csrf`, no new `allow_guest` endpoint, no new CORS entry.
- [ ] Both sides check `event.source` and `event.origin`; no `*` target.
- [ ] No message mutates a flow or runs anything.
- [ ] Theme values validated by allow-list; no CSS string injection.
- [ ] Server permissions and publish checks unchanged; palette not relied on for security.
- [ ] Unknown `app` fails closed.
- [ ] Frame never navigates to `/login` or out of the editor.
- [ ] G2, G3 and G5 untouched: embed mode adds no send path, changes no `live_send` or `dry_run` handling.

## 10. Acceptance tests for H-W7-02 to H-W7-06

### H-W7-02 palette (server test and vitest)

1. `list_node_types(app="x")` returns only `x` app types plus allow-listed built-ins; a second app's types are absent.
2. `code.run`, `tool.call`, `doc.create`, `doc.update` are absent even for System Manager.
3. A fake ledger-kind node appears only when the scoped app registers it; no `ledger_write` entry exists (G1).
4. Unknown `app` raises; no `app` returns today's result; a user without Flow Definition read is refused.
5. Vitest: every add-step path offers only scoped types; an existing out-of-scope step is read-only and survives a save unchanged.

### H-W7-03 theme (vitest)

1. Each token in section 5 sets its variable; unknown names are ignored.
2. `url(...)`, `var(...)`, `red;}`, over-long font lists and out-of-range lengths are dropped.
3. `mode` switches `data-theme` without writing `localStorage`; a later system-theme change does not override it.
4. No tokens leaves the root element unstyled; `check-design-parity.mjs` passes. Screenshot in light and dark, opened and checked.

### H-W7-04 route (`huf/ai/tests/test_embed_headers.py` and vitest)

1. No config: `frame-ancestors 'none'`. `'self'` and a valid origin appear when configured.
2. `*`, `https://a.example/path`, `https://a.example; script-src *`, and `http://` outside developer mode are dropped.
3. Guest, user without `flows.use`, and user without flow read get 403 with the header.
4. `/huf/flows/<id>` headers are unchanged.
5. Vitest: the embed route renders no sidebar or global command palette; an expired session shows the signed-out state and does not change `window.location`; leaving links emit `guest.navigate`.
6. Screenshot of the embedded editor, opened and checked.

### H-W7-05 mount package (vitest)

1. Messages with a foreign origin, foreign source, wrong `ns` or `v`, or oversize payload are ignored, on both sides.
2. No `postMessage` call uses `*`.
3. Every guest message has exactly the keys in section 4.2; a seeded sentinel string placed in flow name, step settings and server error text never appears in any message (G4).
4. Attribute changes reload or re-theme as section 7 says; the 20 second fallback fires without `guest.ready`.
5. `yarn build` emits the stable bundle; `yarn tsc --noEmit` is clean.

The guest-side bridge (sending messages from the editor) is part of H-W7-05; its file scope must include the embed page under `frontend/src/` that H-W7-04 adds.

### H-W7-06 e2e (Playwright)

1. A host fixture on the same origin embeds the editor; the user edits, saves and publishes; the saved version matches `guest.saved`.
2. Out-of-scope steps are not offered.
3. A foreign origin cannot frame the page, and its messages have no effect.
4. The whole journey edit happens without visiting `/huf` at top level.
5. Add a usage section to this document.

## 11. Not in v1

Cross-site hosts and token auth; flow list, creation or deletion inside the frame; host-triggered save or publish; auto-resize; web-font loading; per-app restriction of which flows a user may open (that is `Flow Definition` permission work).
