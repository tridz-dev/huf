# God-Component Fix Plans

Concrete, per-component remediation plans for every entry in
[`god-component-inventory.md`](./god-component-inventory.md). Ordered by priority:
user-facing form pages first, shared chat components next, flow-builder and shared UI
primitives after that, admin pages last, exempt entries at the end.

**Sources of truth:**
- Inventory + verified counts: `docs/architecture/god-component-inventory.md`
- Review spec (the "Improvements" list this doc implements): `intake/review-DOC-god-component.md`
- Adopted schema-driven plan: `plans/PR-156-schema-driven-forms.md` (v2, all 8 critique findings adopted)

Every plan below was written **after reading the actual component file** on this branch.
All cited structures (sub-components, hooks, sections, line ranges) exist in the code as
of 2026-07-20. If a citation drifts, re-verify before starting the PR (see
"How to execute one component PR" at the bottom).

## Sequencing legend

| Tag | Meaning |
|:----|:--------|
| **schema-pilot** | Covered by the PR-156 plan phases (Phase 0 regression suite → Phase 1 `transforms.ts` + domain hooks → Phase 2 per-tab typed `FieldDefinition[]` + `FormRenderer`, scalar fields only). This doc does NOT duplicate that plan; it only maps the component to its phase. |
| **follow-on-adopter** | Adopts the schema-driven pattern after the pilot proves out (PR-156 plan Phase 3), reusing `FormRenderer` and the per-tab `FieldDefinition[]` conventions. |
| **standalone-split** | Not a schema-driven form candidate (lists, modals, canvases, primitive libraries). Split along the real seams cited below, in its own PR(s). |
| **exempt** | Deliberately not split, with rationale. |

**Schema terminology (per review Finding 4):** the refactor moves agent form fields to
**per-tab TypeScript `FieldDefinition[]` schemas** (`fields/<tab>.fields.ts`) — NOT a
centralized JSON schema config, which would recreate the god component in config form
(PR-156 plan, amendment A2). Zod stays the single source of truth for validation (A3).
The Triggers/Tools/Knowledge tabs are child-table / side-entity workflows and are
**explicitly out of scope** for the Phase-2 `FormRenderer`; they keep dedicated components.

## Summary table

| # | Component | Lines / `useState` | Sequencing | Effort |
|--:|:--|:--|:--|:--|
| 1 | `pages/AgentFormPage.tsx` | 1902 / 48 | schema-pilot (Phases 0–2) | L |
| 2 | `agent/AdvancedTab.tsx` | 768 / 0 | schema-pilot (Phase 2) | M |
| 3 | `tools/ToolCreationForm.tsx` | 1037 / 7 | follow-on-adopter (Phase 3) | M |
| 4 | `pages/AgentPromptFormPage.tsx` | 736 / 14 | follow-on-adopter (Phase 3) | M |
| 5 | `pages/AgentSummaryPromptFormPage.tsx` | 625 / 10 | follow-on-adopter (Phase 3) | S |
| 6 | `tools/SelectToolsModal.tsx` | 393 / 12 | standalone-split | S |
| 7 | `knowledge/KnowledgeInputsModal.tsx` | 408 / 12 | standalone-split | S |
| 8 | `category/CategoryModal.tsx` | 604 / 8 | standalone-split | M |
| 9 | `ai-elements/prompt-input.tsx` | 1366 / 7 | standalone-split | L |
| 10 | `chat/ChatListing.tsx` | 692 / 7 | standalone-split | M |
| 11 | `chat/ChatInput.tsx` | 716 / 4 | standalone-split | M |
| 12 | `ai-elements/message.tsx` | 448 / 3 | standalone-split | S |
| 13 | `ai-elements/context.tsx` | 408 / 0 | standalone-split | XS |
| 14 | `RightSidebar.tsx` | 1210 / 15 | standalone-split | L |
| 15 | `modals/NodeSelectionModal.tsx` | 680 / 10 | standalone-split | M |
| 16 | `FlowCanvas.tsx` | 452 / 7 | standalone-split | M |
| 17 | `contexts/FlowContext.tsx` | 468 / 10 | standalone-split | M |
| 18 | `ui/sidebar.tsx` | 707 / 2 | standalone-split (low value) | XS |
| 19 | `ui/jsx-preview.tsx` | 649 / 3 | standalone-split | S |
| 20 | `pages/McpDetailsPage.tsx` | 717 / 10 | standalone-split | M |
| 21 | `mcp/ConnectionTab.tsx` | 567 / 4 | standalone-split | M |
| 22 | `pages/ModelsPage.tsx` | 581 / 9 | standalone-split | M |
| 23 | `pages/AiProvidersPage.tsx` | 418 / 8 | standalone-split | S |
| 24 | `pages/IntegrationSettingsDetailsPage.tsx` | 491 / 10 | standalone-split | M |
| 25 | `pages/AgentRunDetailPage.tsx` | 485 / 8 | standalone-split | S |
| 26 | `pages/DataTableBuilderPage.tsx` | 415 / 4 | standalone-split | S |
| 27 | `pages/ConsolePage.tsx` | 212 / 12 | standalone-split | XS |
| 28 | `pages/UsersPage.tsx` | 346 / 11 | standalone-split | S |
| 29 | `App.tsx` | 502 / 0 | **exempt** | — |

---

## A. User-facing form pages

### 1. `AgentFormPage.tsx` — schema-pilot (PR-156 plan, Phases 0–2) · L

**Verified:** 1902 lines, 48 `useState`. Form values already live in react-hook-form + Zod
(`useForm<AgentFormValues>({ resolver: zodResolver(agentFormSchema) })` at lines 290–291;
schema in `components/agent/types.ts`). The 48 `useState` are async/resource/modal/UI state.
Tab UIs are already extracted (`GeneralTab`, `BehaviorTab`, `TriggersTab`, `ToolsTab`,
`KnowledgeTab`, `PermissionsTab`, `AdvancedTab` under `components/agent/`); the remaining
god-ness is hook-level: ~14 `useEffect`s and ~30 handlers.

**Do NOT propose react-hook-form adoption — it already exists** (review Finding 2).

**Plan: execute the PR-156 plan as written.** Phases, mapped to real seams in this file:

- **Phase 0 — regression suite.** Cover: transform round-trips, hidden-tab validation
  routing, dirty-guard behavior, create/edit save payload shapes. Gate for everything below.
- **Phase 1 — `transforms.ts` + domain hooks.** Centralize the Frappe `0/1↔boolean` /
  list↔csv conversions currently inlined in `mapAgentDocToFormValues` (lines 67–126) and the
  load effect, then extract the verified state/handler clusters:
  - `useAgentLoad` — agent doc load incl. tools enrichment, triggers, MCP enrichment,
    knowledge rows, stats (lines 843–1020; note the unreachable dead `else` branch at
    ~847–910 flagged by an inline "resolved merge conflict" comment — delete it).
  - `useAgentSave` — `onSubmit` (1023–1321, ~300 lines) with its duplicated post-save
    enrichment blocks (957–999 vs 1264–1305).
  - `useAgentDirty` — the `toolsChanged`/`disabledChanged`/`mcpServersChanged`/
    `knowledgeChanged` + `showSaveButton`/`hasUnsavedChanges`/`shouldBlock` family (350–433).
  - `useAgentTools` — tool-edit cluster `handleEditTool`/`handleToolFormSubmit` (1417–1493)
    + `toolFormData`/`loadingToolData`.
  - `useAgentMcp` — MCP handlers (1494–1559) + MCP state (278–281) + enrichment (957–982).
  - `useAgentKnowledge` — knowledge state (282–286) + handlers (1561–1598).
  - `useAgentTriggers` — trigger state (261–265) + handlers (1600–1712) + fetch effects
    (436, 461, 936).
  - Also: the two near-identical prompt-option loaders (497–541, 543–587) and the
    prompt-mode clear / version-sync effect pairs (752–818) → shared prompt-template hooks
    mirroring `PromptTemplateSection`; router-state handoff (589–643) + pending-prompt
    resolution (645–726) → `useLinkedResourceHandoff`.
- **Phase 2 — per-tab typed `FieldDefinition[]` + `FormRenderer`**, scalar fields only,
  General tab first, one tab per PR. Triggers/Tools/Knowledge tabs keep their dedicated
  components (child-table workflows — out of renderer scope).

**Risk:** High — most-touched page in the repo; in-flight PRs keep adding fields
(mitigation: PR-156 §3 sequencing; land #414/#362 first, #407 test-runner fix before Phase 0).

**Acceptance (behavioral, per the adopted plan):**
- Phase 0 suite exists and passes before any extraction merges.
- After each phase: load/save/dirty/tool/MCP/knowledge/trigger paths exercised via the
  Phase 0 suite + manual checklist; `yarn typecheck`, `yarn test`, `yarn build` green.
- No visual change in Phases 0–1; Phase 2 renders identical fields from schemas.
- Hidden-tab error field lists are GENERATED from the per-tab schemas, never duplicated (A4).

### 2. `AdvancedTab.tsx` — schema-pilot (PR-156 plan, Phase 2) · M

**Verified:** 768 lines, 0 `useState`. Pure presentational tab receiving
`form: UseFormReturn<AgentFormValues>`; already sectioned into six real
`FormSettingsSection` blocks: "Conversation Strategy" (81–193), "Summarization Engine"
(196–413), "Conversation Data" (416–517), "Huf UI" (519–572), "Model Modality Settings"
(574–687), "Document Upload" (689–765). **Do not rename or re-split these sections**
(review Finding 2) — the file is absorbed by the pilot as the per-tab `advanced.fields.ts`
schema.

**Plan (Phase 2, after General tab proves the pattern):**
- Author `fields/advanced.fields.ts`: one typed `FieldDefinition` per scalar field in the
  six sections above (label as metadata, default, Zod field ref, Frappe transform key,
  `visibleWhen` — e.g. Summarization Engine fields render only when
  `context_strategy === 'Summarize'`).
- Extract the summary-prompt-template sub-block (278–385) into a shared
  `PromptTemplateSelector` — it duplicates the pattern in `PromptTemplateSection`
  (GeneralTab's prompt selector). Dedup, don't copy.
- Extract the three modality filters (63–65) + modality field block (574–687) into
  `useModalityModels` + a `ModelModalitySection` fed by schema entries, since it carries
  real filter logic the other sections don't.

**Risk:** Low–Medium — presentational only, but the conditional Summarization Engine
visibility and version-lock fields must round-trip exactly.

**Acceptance:** All six sections render from `advanced.fields.ts` via `FormRenderer`;
section visibility conditions behave identically (toggle `context_strategy` and verify);
Zod validation and hidden-tab error routing unchanged; `yarn typecheck/test/build` green.

### 3. `ToolCreationForm.tsx` — follow-on-adopter (Phase 3) · M

**Verified:** 1037 lines, 7 `useState`. Uses RHF + Zod with a per-template schema built by
`createToolFormSchema` (`toolCreationForm.utils`). Real internal seams: three in-file render
functions — `renderParameterEditorView()` (393–432), `renderSettingsView()` (433–922),
`renderFunctionDefinitionView()` (924–939); sections "Core configuration" (441–513),
"Operation details" (514–~740), "HTTP Headers" (~711–745), "Parameters" (746–~840 with a
`@tanstack/react-table` table at 803–835), "Additional Settings" (842–921). Existing
extractions to build on: `ParameterCard`, `HttpHeaderCard`, `SelectDocTypeFieldsDialog`,
`useToolCreationOptions`, `toolCreationForm.utils`.

**Plan:**
- First (mechanical split PR): convert the three `render*View` functions into components
  `ParameterEditorView`, `ToolSettingsView`, `FunctionDefinitionView`; extract the tanstack
  table block (columns 319–385 + instance 387–391 + JSX 803–835) into `ToolParametersTable`
  and the "HTTP Headers" block + header handlers (218–234) into `HttpHeaderSettings`.
- Then (schema adoption PR): express "Core configuration", "Operation details" and
  "Additional Settings" scalar fields as typed `FieldDefinition[]` (typed against
  `ToolFormData`), keeping `shouldShowField` visibility logic as schema `visibleWhen`
  metadata. The Parameters child-table and HTTP-headers list stay dedicated components —
  same exclusion rule as the pilot's child-table tabs.

**Risk:** Medium — per-template dynamic schema and `shouldShowField` conditional fields are
the trickiest mapping onto static field definitions; shared-tool edit mode
(`getAgentsUsingTool` warning) must keep working.

**Acceptance:** Create/edit a tool of each major type (Get/Create/Update Document, Custom
Function, GET/POST, Run Agent) with identical rendered fields and identical save payloads;
DocType-meta mandatory-param autofill (139–170) still fires; `yarn typecheck/test/build` green.

### 4. `AgentPromptFormPage.tsx` — follow-on-adopter (Phase 3) · M

**Verified:** 736 lines, 14 `useState`. RHF + `zodResolver(agentPromptFormSchema)` (105–106).
Real seams: version/fork handler quartet + dialog state (`newVersionDialogOpen`,
`newVersionTitle`, `newVersionDescription`, `dialogAction`; handlers 375–431); category
cluster (4 states + 2 effects + debounced auto-save 225–246, `CategoryTab` 645–659,
`CategoryModal` 700–715); usage fetch inside the load effect (118–188); in-file
`isInternalPath` helper (41–57). Existing extractions: `InstructionsTextarea`,
`AgentPromptNewVersionDialog`, `CategoryTab`, `CategoryModal`, `InlineEditName`.

**Plan:**
- Extract `usePromptVersioning` (version/fork handlers + dialog state) and
  `usePromptCategory` (category cluster incl. auto-save) — both are reusable verbatim by
  `AgentSummaryPromptFormPage` (see #5).
- Move `isInternalPath` to a shared `lib/` util (check for existing duplicates first).
- Schema adoption: "Prompt Details" card scalar fields (title, slug, visibility, is_active,
  tags, description) become a typed `FieldDefinition[]`; "Prompt Body" stays
  `InstructionsTextarea`; "Version Info" stays presentational.

**Risk:** Medium — debounced category auto-save and slug auto-generation (204–214) are
side-effecting behaviors easy to break silently.

**Acceptance:** Save / new-version / fork / delete flows unchanged end-to-end; category
auto-save still debounces and persists; version dialog carries title/description through;
shared hooks are consumed by both prompt pages; `yarn typecheck/test/build` green.

### 5. `AgentSummaryPromptFormPage.tsx` — follow-on-adopter (Phase 3) · S

**Verified:** 625 lines, 10 `useState`. **Near-verbatim structural twin of
`AgentPromptFormPage`** (~85% identical: same-shaped in-file schema, `mapDocToFormValues`,
load effect, save/version/fork/delete handlers, JSX skeleton) minus the category system.

**Plan:**
- Adopt the shared hooks from #4 (`usePromptVersioning`, plus a shared `usePromptLoad`)
  and collapse the duplicated JSX into a shared `PromptFormView` parameterized by API
  module (`agentPromptApi` vs `agentSummaryPromptApi`) and title strings.
  `AgentPromptFormPage` then only adds the category feature on top.
- Schema adoption mirrors #4 ("Summary Prompt Details" card, 474–~564).

**Risk:** Low — the twin structure makes divergence the main hazard; diff the two pages
before and after to confirm only intended differences remain.

**Acceptance:** Both prompt pages render and save identically to before; the duplicated
~400 lines of shared skeleton exist exactly once; `yarn typecheck/test/build` green.

### 6. `SelectToolsModal.tsx` — standalone-split · S

**Verified:** 393 lines, 12 `useState` (under 400 lines but violates the 10-`useState`
rule). Already imports well-factored pieces (`ToolCard`, `ToolTemplateCard`,
`ToolCreationForm`). Real seams: load+usage-map effect (62–106) with an **N+1 fan-out** of
`getAgentsUsingTool(tool.name)` per tool (75–86); `handleFormSubmit` (196–248); memo block
`toolTypesMap`/`toolTypeOptions`/`filteredTools` (116–150); create-tab view switch (337–362).

**Plan:**
- Extract `useToolLibraryData(open, selectedTools)` — load effect + memo block — and fix
  the N+1 (batch the usage lookup or defer it behind expansion).
- Extract `useCreateTool` mutation hook from `handleFormSubmit`.
- Extract `CreateToolTab` (template grid vs `ToolCreationForm` switch).

**Risk:** Low — cleanest of the modals; the only behavioral change is the N+1 fix, which
needs its own verification.

**Acceptance:** Open modal → library list, search, type filter, selection count all behave
as before; creating a tool from a template refreshes the list; network panel shows no
per-tool `getAgentsUsingTool` waterfall on open; `yarn typecheck/build` green.

### 7. `KnowledgeInputsModal.tsx` — standalone-split · S

**Verified:** 408 lines, 12 `useState`. Real seams: create-form panel (250–339) with its 5
form-field states + `resetForm`/`handleUploadFile`/`handleCreate` (113–201); input row
(351–400); helpers `getInputStatusVariant`/`getInputIcon`/`getInputPreview` (37–72);
`loadInputs` + delete/reprocess reload pattern (95–105, 203–226).

**Plan:**
- Extract `KnowledgeInputCreateForm` (the File/Text/URL type-switched panel + upload
  progress) or a `useKnowledgeInputForm` hook.
- Extract `KnowledgeInputRow` (status badge, chunk count, error text, Reprocess/Delete).
- Move the three `getInput*` helpers to utils.
- Extract `useKnowledgeInputs(knowledgeSource)` data hook (load + reload-after-mutation).

**Risk:** Low — self-contained modal; upload-progress lifecycle is the only fiddly part.

**Acceptance:** Create each input type (File upload with progress, Text, URL), reprocess,
and delete all work against a real Knowledge Source; list reloads and `onSourceChanged`
fires after every mutation; `yarn typecheck/build` green.

### 8. `CategoryModal.tsx` — standalone-split · M

**Verified:** 604 lines, 8 `useState`. Manual `useState` form (no RHF). Real seams: List
tab (265–443) containing `CategoryRow` markup (344–423) and "Selected category" card
(306–333); Create/Edit tab (446–599: name, description, icon Select from `TABLE_ICONS`,
color picker, parent select); reset-form literal duplicated 4× (81–87, 197–203, 226–232,
585–591); `handleCreate` create/update branching (154–242); icon-resolution expression
duplicated at 302–303 and 340–341.

**Plan:**
- Extract `CategoryListTab` (with `CategoryRow` and `SelectedCategoryCard`) and
  `CategoryFormTab`.
- Extract `useCategoryMutations` from `handleCreate`/update/delete handlers; the 4×
  duplicated reset literal collapses into one `emptyCategoryForm()` factory.
- Hoist the duplicated icon-resolution expression into one helper.

**Risk:** Medium — three modal modes (select / add / edit) share one form state object;
mode transitions reset state through the duplicated literals and are easy to regress.

**Acceptance:** All three modes round-trip: select+save selection, create, edit, delete —
each against the prompts page that embeds this modal; form resets cleanly between modes;
`yarn typecheck/build` green.

---

## B. Shared chat components

### 9. `prompt-input.tsx` — standalone-split · L

**Verified:** 1366 lines, 7 `useState`. A dependency-free primitive library (~30 exports).
Real seams (review Finding 2 corrections applied — **no token-counting or pricing
indicators exist in this file**; do not plan a `PromptTokenCounter`):
- Attachments subsystem: `AttachmentsContext` (78–250), `PromptInputAttachment` (270),
  `PromptInputAttachments` (368), `PromptInputActionAddAttachments` (397), the provider vs
  local dual-mode (`ProviderAttachmentsContext` 103–108 vs `LocalAttachmentsContext` 250)
  — the two near-duplicate attachment contexts are the real smell.
- Drop-zone effects: form-level drag/drop (593), global drag/drop (618) + `addLocal`
  validation (482–651).
- `PromptInputSpeechButton` + 40-line SpeechRecognition type declarations (1021–1168).
- Action menu / header-button family: `PromptInputActionMenu*` (946–982),
  `PromptInputHeader`/`Footer`/`Tools`/`Button` (887–945), `PromptInputSubmit` (991).
- ~600-line tail of one-line shadcn re-export wrappers: Select (1172–1221), HoverCard
  (1225–1250), Tabs (1254–1303), Command (1307–1366).

**Plan:**
- Extract `PromptAttachmentManager` — unify the provider/local attachment contexts behind
  one manager with a mode prop, plus the chip/hover-card/list components →
  `prompt-input-attachments.tsx`.
- Extract `usePromptInputFileDrop` (both drop-zone effects + file validation).
- Extract `PromptInputSpeechButton` + SpeechRecognition declarations → own module.
- Split the wrapper tail by family (`prompt-input-select.tsx`, `prompt-input-tabs.tsx`,
  `prompt-input-command.tsx`) — mechanical, keep export names identical.
- Extract the action-menu/header/footer/submit family → `prompt-input-actions.tsx`.

**Risk:** High-ish — this is a public API surface consumed by chat and by PR #210's work;
export names and context behavior must not change. Dual-mode attachments have subtle
fallback semantics (`useOptional*` accessors).

**Acceptance:** Every existing import of this file resolves unchanged (barrel re-exports
preserved); attach-by-button, attach-by-drag-global, attach-by-paste, and speech input all
work in the chat UI in both provider and local modes; `yarn typecheck/test/build` green.

### 10. `ChatListing.tsx` — standalone-split · M

**Verified:** 692 lines, 7 `useState`. **Review-corrected seams** (earlier recommendations
naming `ChatSearchHeader`/`ConversationMenu` were wrong: no search/filter UI exists here,
and `ConversationMenu` is already extracted — imported at line 27):
- In-file components: `AgentConversationItem` (279–444), `RecentsConversationList`
  (446–635), `ChatListHeader` (637–679); helpers `getRecentBucketLabel` (29–42),
  `LIST_TABS` (681–692).
- `huf:conversation-created` window-event listener effect (113–181).
- `getAgentsWithConversationCounts` fetch on mount (80–110).
- Agent color fan-out effect via `getAgent` per unique agent (484–507).
- sessionStorage persistence of open accordions (53–60, 184–191).
- Duplicated menu-click-suppression logic in Link onClick (386–399 and 575–588).

**Plan:**
- Move `AgentConversationItem`, `RecentsConversationList`, `ChatListHeader` to own files
  under `components/chat/`; move `getRecentBucketLabel`/`LIST_TABS` to utils/constants.
- Extract `useConversations` hook: the counts fetch + the `huf:conversation-created`
  listener + refresh logic.
- Extract `useAgentColorMap` from the color fan-out effect.
- Extract `useSessionStorageState` for accordion persistence.
- Collapse the duplicated click-suppression handler into one shared helper.

**Risk:** Medium — imperative ref-maps (`titleRefs`, `recentsAddItemRef`,
`agentAddItemRefs`) cross the component boundaries being split; the custom-event contract
(`huf:conversation-created`) is implicit.

**Acceptance:** By-Agent and Recents tabs render identical groupings and counts; creating
a conversation from elsewhere in the app updates the list without reload; accordion
open-state survives tab switches; inline title editing still works through the refs;
`yarn typecheck/build` green.

### 11. `ChatInput.tsx` — standalone-split · M

**Verified:** 716 lines, 4 `useState`. Single component; the bulk is three near-identical
send pipelines sharing optimistic-insert/error-rollback logic: staged-file branch in
`handleSubmit` (163–286), plain-text branch (288–349), and `handleAudioRecorded` (352–462).
Other seams: file staging (`handleFileSelected` 472–521 + `pendingFile` state 58–65 +
`readFileAsBase64` 143–153), textarea auto-resize (`adjustTextareaHeight` + effect
531–588), model-mismatch "New Conversation" panel (600–619), pure helpers
`runAgentAndUpdateAssistant`/`syncAssistantMessageId` (82–141). Already imports
`SpeechInput` and `ChatAttachmentCard`.

**Plan:**
- Extract `useSendAgentMessage` hook unifying the three pipelines (optimistic
  user/assistant insertion, `updateAssistantContent`, error rollback,
  `onConversationCreated` bookkeeping).
- Extract `useFileStaging` (pending-file lifecycle + upload).
- Extract `useAutosizeTextarea`.
- Move the model-mismatch panel to a small component; move the two pure helpers next to
  the chat services.

**Risk:** Medium — this is the message-send hot path; streaming vs non-streaming branches
and audio-vs-text flows must stay behavior-identical.

**Acceptance:** Send plain text, send with attachment (staged upload then send), and send
audio-recorded message — each verified end-to-end with optimistic UI and error rollback
(failure leaves the user's draft intact); model-mismatch fallback still offers a new
conversation; `yarn typecheck/build` green.

### 12. `message.tsx` — standalone-split · S

**Verified:** 448 lines, 3 `useState`. Primitive library, no data fetching. Real seams:
branch subsystem (`MessageBranchContext` 109–137 + `MessageBranch`/`BranchContent`/
`BranchSelector`/`BranchPrevious`/`BranchNext`/`BranchPage` 139–305); attachment components
(`MessageAttachment` 330–406, `MessageAttachments` 410–430); `MessageResponse` memoized
Streamdown wrapper (309–322); core (`Message`, `MessageContent`, `MessageActions`,
`MessageAction`, `MessageToolbar`).

**Plan:** split by family — `message-branch.tsx`, `message-attachment.tsx`,
`message-response.tsx`, core stays in `message.tsx`. Preserve all export names.

**Risk:** Low — presentational; only `useMessageBranch` context pairing must survive.

**Acceptance:** Existing consumers (`chat/*` renderers) render messages, branch navigation,
and attachments unchanged; `yarn typecheck/build` green.

### 13. `context.tsx` — standalone-split · XS

**Verified:** 408 lines, 0 `useState`. Stateless usage-meter primitives. Real smell: the
four usage-row components (`ContextInputUsage` 233, `ContextOutputUsage` 273,
`ContextReasoningUsage` 313, `ContextCacheUsage` 353) are ~95% duplicated; cost
calculation blocks repeat in the footer + 4 rows; `ContextIcon` SVG donut (63–102);
`TokensWithCost` + repeated `Intl.NumberFormat` formatters (391–408).

**Plan:** collapse the four rows into one parameterized `ContextUsageRow`; extract
`getCostUSD(modelId, usage)` helper and a shared currency/compact formatter; move
`ContextIcon` to its own file.

**Risk:** Low.

**Acceptance:** Usage hover-card shows identical percentages, per-row token counts, and
costs for a model with and without cache/reasoning usage; `yarn typecheck/build` green.

---

## C. Flow builder

### 14. `RightSidebar.tsx` — standalone-split · L

**Verified:** 1210 lines, 15 `useState`. This is the flow builder's **selected node/edge
configuration panel** — review-corrected: there are no Context/ExecutionProperties/
RunHistory panels. Real structure: `renderTriggerForm` (189–359) with per-type forms
(webhook 196–246, schedule 248–293, doc-event 295–331, app-trigger 333–356); a giant
action-config IIFE (506–1126) with per-type forms (`agent-run` 522–566, `tool-call`
568–647, `router` 649–686, `human.approval` 688–810, `condition` 812–855, `http-request`
857–953, `transform` 955–1043, `loop` 1045–1113); edge config panel (386–457); four
async option-list effects (agents 73–91, tools 94–108, DocTypes 133–147, roles 150–162)
plus tool-schema fetch (111–130); resize logic (37–38, 52–70); repeated
"label + `VariablePicker` + input" field pattern (539–553, 712–727, 819–834, 861–876);
delete dialog (1150–1174).

**Plan:**
- Split per node type: `TriggerConfigPanel` (webhook/schedule/doc-event/app-trigger
  sub-forms) and action forms `AgentRunForm`, `ToolCallForm`, `RouterForm`,
  `HumanApprovalForm`, `ConditionForm`, `HttpRequestForm`, `TransformForm`, `LoopForm`;
  plus `EdgeConfigPanel`.
- Extract `useFlowOptionLists(selectedNode)` — the four option-list effects share one
  load/map/catch/finally pattern — and `useToolDetails(toolName)`.
- Extract `useResizablePanel` (width/isResizing + mousemove/up listeners).
- Extract `VariableInput` for the repeated VariablePicker field pattern; move the delete
  dialog to `DeleteNodeDialog`.

**Risk:** High — forms write straight into `useFlowContext().updateNode`; a missed config
key silently drops user data. Nine per-type forms is a big single PR — split into 2–3 PRs
(triggers+edge first, then actions).

**Acceptance:** For each node type, select node → edit every config field → verify the
flow definition JSON updates identically to before (diff `definition_json` before/after);
option lists load lazily per node type as before; panel resize persists during session;
`yarn typecheck/build` green.

### 15. `NodeSelectionModal.tsx` — standalone-split · M

**Verified:** 680 lines, 10 `useState`. Real seams: four inline trigger config forms inside
`renderTriggerForm` — webhook (211–293), schedule (295–346), doc-event (348–391),
app-trigger (393–416); `renderActionCategory` grid (421–456); agent card list item
(530–576); trigger card markup duplicated between Highlights (589–608) and Popular
(619–643); `handleSelectAction` config-factory switch (177–200); `iconMap` (53–69);
data effects (DocTypes 96–109, agents 111–122).

**Plan:**
- Extract the four trigger config forms into components (shared with — not duplicated
  from — `RightSidebar`'s trigger forms if the timing works out; otherwise extract here
  first and converge later — call this out in the PR).
- Extract `ActionCategoryGrid` and `AgentCardItem`; collapse Highlights/Popular card
  duplication into one `TriggerCard`.
- Extract `useNodeSelectionData(open, subTab)` for the two fetch effects; move `iconMap`
  next to `triggerOptions`/`actionOptions` data.

**Risk:** Medium — the modal both selects AND configures; the `triggerConfig` handoff into
`onSave` must stay exact for `FlowCanvas`'s node creation.

**Acceptance:** Create each trigger type and each action category from the canvas; saved
node configs match the pre-split shapes; search and sub-tab filtering behave as before;
`yarn typecheck/build` green.

### 16. `FlowCanvas.tsx` — standalone-split · M

**Verified:** 452 lines, 7 `useState`. Real seams: sync-from-context + 50ms debounced
write-back machinery (47–109) with `isSyncingFromProps`/`pendingUpdateRef`/
`updateTimeoutRef` guards; ReactFlow change handlers (111–151); `handleSaveTriggerConfig`
node create/update (183–238); `handleSelectAction` node-insert-with-edge-rewire (240–328);
`iconMap`/`labelMap` duplicated in two handlers (185–197 vs 250–276); canvas chrome Panels
(379–436).

**Plan:**
- Extract `useFlowGraphSync` (the sync/debounce block + change handlers).
- Extract node-mutation helpers `createTriggerNode` / `insertActionNode` from the two
  handlers; hoist the duplicated `iconMap`/`labelMap` to one shared module (also used by
  `NodeSelectionModal`).
- Extract `CanvasChrome` (the three corner Panels).

**Risk:** Medium — the debounced two-way sync between ReactFlow state and FlowContext is
race-prone; the split must not change ordering.

**Acceptance:** Add/move/connect/delete nodes and edges; reload the page and confirm the
flow persists exactly; rapid edits don't lose the last change (debounce flush);
`yarn typecheck/build` green.

### 17. `FlowContext.tsx` — standalone-split · M

**Verified:** 468 lines, 10 `useState`. Added to the inventory by the review (Finding 5) —
exactly the co-located-state pattern the inventory warns about. Real seams: realtime
window-event listeners `frappe:flow_node_start/end`, `frappe:flow_paused/completed/error`
(156–233) with a node-status updater repeated in all 5 handlers (161–218); CRUD
passthroughs (241–272); six near-identical node/edge mutators (300–403, same
setState + `lastSyncedFlowRef` + flowService + `markUnsaved` pattern); `flowsEqual`
deep-equality helper (38–53); giant `useMemo` value (405–457).

**Plan:**
- Extract `useFlowRealtimeSync(activeFlowId, ...)` — listener block + one shared
  node-status updater.
- Collapse the six mutators onto one internal `mutateActiveFlow(fn)` helper (keep the
  public method names).
- Optionally split provider state by domain (definition state vs execution/selection
  state) — only if a consumer demonstrates re-render pain; otherwise defer and say so.

**Risk:** Medium — every flow-builder component consumes this context; the
sync-guard refs (`hasFetchedRef`, `lastSyncedFlowRef`, `activeFlowRef`) are load-bearing.

**Acceptance:** Flow list load, active-flow switch, node/edge edits, save, and realtime
status updates (run a flow and watch node states flip) all behave as before;
`yarn typecheck/build` green.

---

## D. Shared UI primitives

### 18. `sidebar.tsx` — standalone-split (low value) · XS

**Verified:** 707 lines, 2 `useState`. Stock vendored shadcn sidebar with HUF theme tweaks
(note comment at line 524). Stateful logic lives only in `SidebarProvider` (54–165:
controlled/uncontrolled open, localStorage, ⌘B shortcut) and `Sidebar` (167–270: three
render branches incl. mobile `Sheet`); the remaining ~18 exports are presentational
forwardRef wrappers.

**Plan:** optional, cosmetic-only: `sidebar-provider.tsx` (context + `useSidebar` +
provider), `sidebar.tsx` (the `Sidebar` component), `sidebar-menu.tsx` (Menu* family,
497–707). **Low refactor value beyond file splitting — do this only when the file is
touched for another reason**; keep it byte-comparable to upstream shadcn where possible so
future vendor updates stay easy.

**Risk:** Low (but churn against upstream shadcn updates is the real cost).

**Acceptance:** App shell renders, ⌘B toggles, mobile sheet works, localStorage
persistence unchanged; `yarn typecheck/build` green.

### 19. `jsx-preview.tsx` — standalone-split · S

**Verified:** 649 lines, 3 `useState`. Bulk is registries, not god-logic. Real seams:
`availableComponents` registry (168–324, ~155 lines); `defaultBindings` helpers (327–382);
`autoCompleteJsx` streaming tag-closer (132–164); `JSXPreviewExport` + SVG helpers
(534–647); context + `useJSXPreview` (113–129). Sibling parsers already live in utils
(`jsxPreambleParser`, `jsxPostProcessor`).

**Plan:** extract `jsxPreviewComponents.ts` (registry), `jsxPreviewBindings.ts`,
move `autoCompleteJsx` next to the other JSX utils, and `JSXPreviewExport` +
context/hook to own files.

**Risk:** Low–Medium — the `JsxParser` component registry is security-sensitive (what
agent-generated JSX may render); moving it must not widen the allow-list.

**Acceptance:** Render a generative-UI JSX artifact with charts and shadcn components;
PNG/SVG export works; an unsupported component is still rejected;
`yarn typecheck/build` green.

---

## E. Admin pages

### 20. `McpDetailsPage.tsx` — standalone-split · M

**Verified:** 717 lines, 10 `useState`. Tab UIs already extracted (`MCPHeader`,
`DetailsTab`, `ConnectionTab`, `ToolsTab`). Real seams: `tabConfig` + 4 `useMemo`
derivations + hash listener (46–140); doc→form reset mapping repeated **4× verbatim**
(212–243, 314–345, 359–390, 567–598); payload builder duplicated in `onSubmit` and
`handleSaveAndConnect` (273–296, 528–551); tool handlers `handleSyncTools`/
`handleTestConnection`/`handleToolToggle` (427–515); delete dialog (693–713).

**Plan:**
- Extract shared `useHashTabs(tabConfig)` — the pattern is near-verbatim in
  `IntegrationSettingsDetailsPage` (84–168) too; one hook, two consumers.
- Extract `mcpDocToFormValues(doc)` and `buildMcpPayload(values)` — kills both 4× and 2×
  duplications.
- Extract `useMcpTools` (sync/test/toggle handlers); delete dialog → shared
  `DeleteConfirmDialog` (also consumed by #24).

**Risk:** Medium — OAuth connect/save-and-connect flows depend on exact payload shapes.

**Acceptance:** Create server (name auto-derived from URL), edit, save, save-and-connect,
sync tools, toggle a tool, test connection, delete — all against a real MCP Server doc;
`yarn typecheck/build` green.

### 21. `ConnectionTab.tsx` — standalone-split · M

**Verified:** 567 lines, 4 `useState`. Real seams: OAuth connect/popup-poll logic
(`handleConnectOAuth` 79–150, `handleDisconnectOAuth` 152–177, `popupRef`/`pollRef`);
"MCP Server URL" card (182–257); OAuth overrides block (365–501); Custom Headers
field-array (503–562, RHF `useFieldArray`); auth-type → header-name auto-fill effect
(62–73).

**Plan:** extract `useMcpOAuth` (popup + poll + status + cleanup), `ServerUrlCard`,
`OAuthOverridesFields`, and a generic `CustomHeadersFieldArray` (reusable — the same
header-row pattern exists in `ToolCreationForm`'s `HttpHeaderCard` usage).

**Risk:** Medium — the OAuth popup/poll lifecycle leaks timers if the cleanup regresses.

**Acceptance:** Complete an OAuth connect flow (popup → poll → connected badge), disconnect,
and verify poll timers stop on unmount; auth-type switch still auto-fills/clears the
header name; custom headers add/remove round-trips through the form;
`yarn typecheck/build` green.

### 22. `ModelsPage.tsx` — standalone-split · M

**Verified:** 581 lines, 9 `useState`. Real seams: Configure/Add Model dialog (397–578,
~180 lines) with Custom Pricing section (476–551); model card `renderItem` (334–382);
deep-link `?configure=` effect (210–246) — near-copy of `AiProvidersPage` (159–195);
manual `formData` state (not RHF); `buildModelPayload` + `handleSave` (248–299).

**Plan:** extract `ModelFormDialog` (with `CustomPricingFields`), `ModelCard`, shared
`useConfigureDeepLink` (one hook for this page and #23), and `useModelForm`
(payload/save). Optionally normalize the manual `formData` to RHF+Zod — call it out as a
separate decision in the PR, don't smuggle it in.

**Risk:** Low–Medium — custom-pricing enable/disable semantics (pricing Switch + 3 cost
inputs) must round-trip 0-values correctly (0 is a valid price for free models).

**Acceptance:** Add/edit a model with and without custom pricing incl. explicit `0` costs;
deep-link `?configure=<model>` opens the dialog pre-filled; infinite scroll and filter
unchanged; `yarn typecheck/build` green.

### 23. `AiProvidersPage.tsx` — standalone-split · S

**Verified:** 418 lines, 8 `useState`. Real seams: Configure Provider dialog (339–415);
provider card `renderItem` (275–323); deep-link effect (159–195, near-copy of
ModelsPage's); manual `formData`; `getModelCountForProvider` (115).

**Plan:** extract `ProviderFormDialog`, `ProviderCard`, shared `useConfigureDeepLink`
(from #22), `useProviderForm`.

**Risk:** Low — API key field is write-only password; ensure edit mode doesn't echo or
clobber an unset key.

**Acceptance:** Add/edit provider (leaving API key blank on edit preserves the stored
key); brand suggestion from name still fires; deep-link works; `yarn typecheck/build` green.

### 24. `IntegrationSettingsDetailsPage.tsx` — standalone-split · M

**Verified:** 491 lines, 10 `useState`. Tab UIs already extracted (`IntegrationHeader`,
`GeneralTab`, `CredentialsTab`, `RecipientsTab`, `TelegramTab`). Real seams: tab/hash
pattern (84–168, shared with #20); `docMeta` state object; delete dialog (466–486);
`handleSetupWebhook` (369–391); `validateCredentials` (252–266).

**Plan:** consume shared `useHashTabs` and `DeleteConfirmDialog` (from #20); extract
`useTelegramWebhook`; move `validateCredentials` to `integration.types` utils; fold
`docMeta` into the form or a `useIntegrationDocMeta` hook.

**Risk:** Medium — conditional Telegram tab and credential-schema-driven fields must keep
matching the server's `required_credentials` JSON.

**Acceptance:** Edit credentials for a schema-bearing service (e.g. Slack), save, reload —
values persist; Telegram webhook setup reports success/failure as before; recipients add/
remove works; `yarn typecheck/build` green.

### 25. `AgentRunDetailPage.tsx` — standalone-split · S

**Verified:** 485 lines, 8 `useState`. Real seams: in-file `RunArtifactsPanel` (52–98,
already a clean sub-component → move to own file); `columns` def (158–242, ~85 lines) →
`childRunColumns.tsx`; overview rows (321–383) → `RunOverviewGrid`/`KeyValueRow`;
Prompt/Response cards (387–415) → `PromptResponseCards` (pattern repeated in
`ConsolePage`); orchestration table (420–479) → `ChildRunsTable`.

**Plan:** mechanical extraction as above; no behavior change.

**Risk:** Low.

**Acceptance:** Open a run with child orchestration runs and artifacts: overview, token/
cost column, prompt/response, artifacts links, sortable child-runs table all render as
before; `yarn typecheck/build` green.

### 26. `DataTableBuilderPage.tsx` — standalone-split · S

**Verified:** 415 lines, 4 `useState` + 1 `useReducer`. UI panels already extracted
(`TableBuilderCanvas`, `FieldConfigPanel`, `TableSettingsPanel`). Real seams:
`builderReducer` + types (16–130, ~75 lines); `handleAddField` naming logic (184–208);
`handleSave` validation+payload (210–263); `sidebarContent` block (282–331); mobile Sheet
vs desktop aside (362–391).

**Plan:** move the reducer to `data-table/builderReducer.ts` (or `useTableBuilder`);
extract `useTableBuilderSave`; `BuilderSidebar` + `ResponsiveConfigPanel` components.

**Risk:** Low–Medium — dirty-guard (`beforeunload` + `useBlocker`) must keep firing from
reducer `isDirty`.

**Acceptance:** Build a table schema, save, re-edit; navigation guard fires with unsaved
changes and stays silent after save; mobile Sheet panel works; `yarn typecheck/build` green.

### 27. `ConsolePage.tsx` — standalone-split · XS

**Verified:** 212 lines, 12 `useState` (under 400 lines; state-rule violation only). Real
seams: agent/provider/model cascade logic (48–61) → `useConsoleSelections`; Response card
(183–208) duplicates `AgentRunDetailPage`'s → shared `RunResponseCard`.

**Plan:** extract the two items above. Lowest-priority refactor on this list.

**Risk:** Low.

**Acceptance:** Pick agent → provider/model cascade narrows correctly; run executes and
response card links to `/executions/{runId}`; `yarn typecheck/build` green.

### 28. `UsersPage.tsx` — standalone-split · S

**Verified:** 346 lines, 11 `useState`. Real seams: in-file `InviteDialog` (73–164, fully
self-contained, own state + `useSaveShortcut`); `ROLE_COLOURS`/`roleBadgeClass` (45–58);
role-change dropdown cell (299–318); `load()` + handlers (187–200) + `filteredUsers` memo
(221–237).

**Plan:** move `InviteDialog` to `components/users/InviteDialog.tsx`; role colours to
`@/utils/status` or `users/roleColours.ts`; `RoleSelectCell`; `useUsers` hook (load +
memo + handlers).

**Risk:** Low.

**Acceptance:** Invite a user with a role, change a role via the dropdown cell, toggle
enabled, filter by search/status — all against real User/Huf Role docs;
`yarn typecheck/build` green.

---

## F. Exempt

### 29. `App.tsx` — exempt-with-rationale

**Verified:** 502 lines, 0 `useState`. Pure root composition: provider nesting
(`SocketProvider > UserProvider > PermissionsProvider > Suspense > Routes`, 74–78) plus
~30 `<Route>` blocks (79–471) repeating the same
`ProtectedRoute > UnifiedLayout(headerActions?) > Suspense(PageLoader) > Page` wrapper
pattern, plus one startup `checkStreamingAvailable()` effect (486–498).

**Rationale for exemption:** the file contains composition, not logic — no state, no data
fetching beyond one startup probe, no conditional complexity. Splitting it would trade a
single scannable route table for indirection without reducing coupling; the 400-line
guideline targets components whose size signals mixed responsibilities, and this file has
exactly one responsibility (route/provider wiring). It is listed explicitly — per review
Finding 5 / Improvement 6 — rather than silently omitted.

**Optional (not required):** if the route table keeps growing, a declarative
`routes.tsx` route-config array would remove the repeated 3–4-layer wrapper boilerplate.
That is a readability nicety, not a god-component fix, and should not block anything.

---

## How to execute one component PR

1. **Branch naming:** `refactor/<component-name>-split` off current `develop`
   (e.g. `refactor/chat-listing-split`). One component per PR; large components
   (AgentFormPage, RightSidebar, prompt-input) split into the staged PRs named in their
   sections above. Schema-pilot/follow-on work branches off the PR-156 phase branches,
   not `develop`, per that plan's sequencing (§3: #407 first, then #414/#362, then phases).
2. **Re-verification ritual (required, from the inventory):** counts drift within days
   (AgentFormPage 1889→1902 and ToolCreationForm 1036→1037 drifted within one week).
   Before writing any code, re-run the scan from the repo root and confirm the target's
   numbers and cited seams; update the inventory doc in the same PR:

   ```bash
   for f in $(find frontend/src -name '*.tsx'); do
     lines=$(wc -l < "$f"); states=$(grep -c useState "$f" || true)
     [ "$lines" -gt 400 ] || [ "$states" -gt 10 ] && echo "$lines / $states  $f"
   done | sort -rn
   ```

   Also spot-check that every structure your plan cites (line ranges, sub-component
   names, hooks) still exists — this doc's citations are a snapshot of 2026-07-20.
3. **Review checklist for the PR:**
   - Every extracted name maps to a real seam that existed in the file (no invented
     panels/hooks); cite old line ranges in the PR description.
   - Acceptance criteria are behavioral and were actually executed — list what you ran
     (flows clicked through, payloads diffed), not line-count deltas.
   - `yarn typecheck`, `yarn test` (where a suite exists), `yarn build` all green.
   - No visual change unless the PR says so; no validation moved out of Zod; no new
     dependencies without calling it out.
   - Export names / public API of shared modules unchanged (barrel re-exports preserved).
   - `docs/architecture/god-component-inventory.md` updated with post-split counts and
     the entry marked done or re-scoped.
   - Frontend strictness: no unused variables/imports (`error TS6133` fails the build).
