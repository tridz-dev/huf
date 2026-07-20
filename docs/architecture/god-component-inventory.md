# God Component Inventory

This document tracks the "god-component" anti-pattern inside the Huf frontend repository, containing a verified inventory of frontend components that exceed the allowable scale threshold, along with recommended splits and remediation directions.

## What is the God-Component Anti-Pattern?

A **god-component** is a monolithic component that takes on too many responsibilities, manages excessive state, contains complex conditional rendering logic, or has grown too large to maintain, test, or read. 

Specifically in React applications, this pattern manifests when components combine:
- Complex UI layouts
- Large forms with dozens of field definitions
- Heavy API communications
- Excessive `useState` and other reactive state hooks

## Why it Hurts THIS Repo

Allowing god-components to propagate has severely impacted development speed and stability in the Huf frontend:
1. **High Overhead for Minor Changes**: Adding a single new agent field requires touching 4+ separate files, resulting in fragmented diffs, merge conflicts, and regression risks.
2. **Brittle Shared Logic**: Features have frequently landed via hand-wired edits to shared pages, leading to regression bugs and tightly coupled code (e.g., Pull Requests #362, #403/#414, and #358/#360).
3. **Severe Performance Lag**: Unnecessary re-renders are triggered across massive component trees because too many independent states are co-located in single parent pages.
4. **Poor Readability & Maintainability**: Comprehending pages containing thousands of lines of mixed formatting, hooks, and modals is extremely difficult for both developers and automated tools.

## Remediation Direction

The primary strategy for resolving god-component sprawl in this repository is transitioning from hand-wired components to **schema-driven configurations** (aligned with the PR #156 architectural plan):

- **Pilot Project**: `AgentFormPage.tsx` (`frontend/src/pages/AgentFormPage.tsx`) is the pilot for the schema-driven form refactor. All individual agent form fields are being moved to a centralized JSON schema config.
- **Follow-on Adopters**: Forms such as `ToolCreationForm.tsx` (`frontend/src/components/tools/ToolCreationForm.tsx`), `AgentPromptFormPage.tsx` (`frontend/src/pages/AgentPromptFormPage.tsx`), and `AgentSummaryPromptFormPage.tsx` (`frontend/src/pages/AgentSummaryPromptFormPage.tsx`) will adopt this schema-driven architecture subsequently, eliminating custom field rendering within page-level files.

---

## Verified God-Component Inventory (>400 Lines)

The following inventory lists all page/view components in the frontend that currently exceed the **400-line threshold** or contain excessive `useState` hooks, verified via active codebase scanning:

### Top Expected Entries

1. **`AgentFormPage.tsx` (`frontend/src/pages/AgentFormPage.tsx`)** (1902 lines, 48 `useState` hooks)
   - *Status*: Drifted from expected 1889 lines to 1902 lines.
   - *Recommended Split*: Transition to the schema-driven form refactor (PR #156). Replace 48 standalone state hooks with a form framework (e.g., `react-hook-form`). Extract tab sections (General, Behavior, Tools, Knowledge, Advanced) and dialog handlers into isolated lazy-loaded child components.

2. **`prompt-input.tsx` (`frontend/src/components/ai-elements/prompt-input.tsx`)** (1366 lines, 7 `useState` hooks)
   - *Status*: Stable at 1366 lines.
   - *Recommended Split*: Extract attachment handling and drag-and-drop logic to `PromptAttachmentManager`. Move token counting and pricing indicators to `PromptTokenCounter`. Extract trigger buttons to `PromptToolbar`.

3. **`ToolCreationForm.tsx` (`frontend/src/components/tools/ToolCreationForm.tsx`)** (1037 lines, 7 `useState` hooks)
   - *Status*: Drifted from expected 1036 lines to 1037 lines.
   - *Recommended Split*: Refactor as a follow-on adopter of schema-driven forms. Separate the parameter list configuration (child table interface) into `ToolParametersTable`. Extract HTTP Headers configuration to `HttpHeaderSettings`.

4. **`AgentPromptFormPage.tsx` (`frontend/src/pages/AgentPromptFormPage.tsx`)** (736 lines, 14 `useState` hooks)
   - *Status*: Stable at 736 lines.
   - *Recommended Split*: Separate the prompt body template editor from the metadata forms. Extract version control modals and list view into a standalone `PromptVersionSelector` component.

5. **`McpDetailsPage.tsx` (`frontend/src/pages/McpDetailsPage.tsx`)** (717 lines, 10 `useState` hooks)
   - *Status*: Stable at 717 lines.
   - *Recommended Split*: Extract the server logs pane to `McpLogConsole`. Break down tool actions and tables into `McpToolsList`. Extract connection configuration options to `McpConfigPanel`.

6. **`ChatListing.tsx` (`frontend/src/components/chat/ChatListing.tsx`)** (692 lines, 7 `useState` hooks)
   - *Status*: Stable at 692 lines.
   - *Recommended Split*: Extract search/filters to `ChatSearchHeader`. Extract conversation list items and action menus to `ConversationListItem` and `ConversationMenu`.

7. **`NodeSelectionModal.tsx` (`frontend/src/components/modals/NodeSelectionModal.tsx`)** (680 lines, 10 `useState` hooks)
   - *Status*: Stable at 680 lines.
   - *Recommended Split*: Divide node types into modular subsections (Trigger Nodes, Action Nodes, Logical Nodes) and extract the search/categorization filter sidebar.

8. **`AgentSummaryPromptFormPage.tsx` (`frontend/src/pages/AgentSummaryPromptFormPage.tsx`)** (625 lines, 10 `useState` hooks)
   - *Status*: Stable at 625 lines.
   - *Recommended Split*: Follow-on adopter of schema-driven forms. Separate the revision table to `SummaryPromptRevisionTable` and isolate the main prompt text editor.

### Additional Over-Limit Components (>400 Lines)

9. **`RightSidebar.tsx` (`frontend/src/components/RightSidebar.tsx`)** (1210 lines, 15 `useState` hooks)
   - *Recommended Split*: Split tab panels into independent components (`ContextPanel`, `ExecutionPropertiesPanel`, `RunHistoryPanel`).

10. **`AdvancedTab.tsx` (`frontend/src/components/agent/AdvancedTab.tsx`)** (768 lines, 0 `useState` hooks)
    - *Recommended Split*: Group advanced fields into isolated fieldsets or sub-sections: `ModelSettingsSection`, `TokenLimitSection`, `SystemTuningSection`.

11. **`ChatInput.tsx` (`frontend/src/components/chat/ChatInput.tsx`)** (716 lines, 4 `useState` hooks)
    - *Recommended Split*: Extract speech-to-text functionality to `SpeechInputButton` and move drag-and-drop attachment layout to `ChatAttachmentDropzone`.

12. **`sidebar.tsx` (`frontend/src/components/ui/sidebar.tsx`)** (707 lines, 2 `useState` hooks)
    - *Recommended Split*: Break down into `SidebarHeader`, `SidebarContent`, `SidebarFooter`, and `SidebarToggleButton` modules.

13. **`jsx-preview.tsx` (`frontend/src/components/ui/jsx-preview.tsx`)** (649 lines, 3 `useState` hooks)
    - *Recommended Split*: Isolate compiler/evaluator logic to `PreviewCompiler` and sandbox rendering to `PreviewSandbox`.

14. **`CategoryModal.tsx` (`frontend/src/components/category/CategoryModal.tsx`)** (604 lines, 8 `useState` hooks)
    - *Recommended Split*: Extract item list rows and inline category editing layout to `CategoryListItem` and creation form to `CategoryForm`.

15. **`ModelsPage.tsx` (`frontend/src/pages/ModelsPage.tsx`)** (581 lines, 9 `useState` hooks)
    - *Recommended Split*: Split into `ModelTable`, `ModelFilters`, and `ModelEditModal` components.

16. **`ConnectionTab.tsx` (`frontend/src/components/mcp/ConnectionTab.tsx`)** (567 lines, 4 `useState` hooks)
    - *Recommended Split*: Isolate connection credentials forms and dynamic status indicators.

17. **`IntegrationSettingsDetailsPage.tsx` (`frontend/src/pages/IntegrationSettingsDetailsPage.tsx`)** (491 lines, 10 `useState` hooks)
    - *Recommended Split*: Split into service description card, configuration credential inputs, and recipient mapping table components.

18. **`AgentRunDetailPage.tsx` (`frontend/src/pages/AgentRunDetailPage.tsx`)** (485 lines, 8 `useState` hooks)
    - *Recommended Split*: Separate the execution header from the run metadata panel and standard log console viewer.

19. **`FlowCanvas.tsx` (`frontend/src/components/FlowCanvas.tsx`)** (452 lines, 7 `useState` hooks)
    - *Recommended Split*: Extract custom edge/node controls and custom context menus to `CanvasControls` and `CanvasContextMenu`.

20. **`message.tsx` (`frontend/src/components/ai-elements/message.tsx`)** (448 lines, 3 `useState` hooks)
    - *Recommended Split*: Extract attachments lists, copy/edit action menus, and Markdown parser to `MessageAttachmentList`, `MessageBubbleActions`, and `MessageMarkdownRenderer`.

21. **`AiProvidersPage.tsx` (`frontend/src/pages/AiProvidersPage.tsx`)** (418 lines, 8 `useState` hooks)
    - *Recommended Split*: Extract provider grid to `ProviderGrid`, credentials setup to `ApiKeyForm`, and model pricing mappings to `ProviderModelTable`.

22. **`DataTableBuilderPage.tsx` (`frontend/src/pages/DataTableBuilderPage.tsx`)** (415 lines, 4 `useState` hooks)
    - *Recommended Split*: Split schema builder canvas, field type selection pane, and settings sidebar into `SchemaDesigner`, `FieldTypeSelector`, and `TableSettingsPanel`.

23. **`context.tsx` (`frontend/src/components/ai-elements/context.tsx`)** (408 lines, 0 `useState` hooks)
    - *Recommended Split*: Move context chip structures and tool status lists into presentation-only sub-components.

24. **`KnowledgeInputsModal.tsx` (`frontend/src/components/knowledge/KnowledgeInputsModal.tsx`)** (408 lines, 12 `useState` hooks)
    - *Recommended Split*: Split modal configuration screens (File upload, Text input, URL scraping) into tabbed content panes (`FileInputPane`, `TextInputPane`, `UrlInputPane`).
