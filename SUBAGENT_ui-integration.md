# Subagent Task: ui-integration

## Mission
Implement UI components for Agent Memory: Agent Memory tab, Memory Explorer, and related interfaces.

## Input Files (READ THESE FIRST)
- `~/code/huf-memory/doctype_designs/memory_record.json` - Memory Record fields
- `~/code/huf-memory/doctype_designs/memory_policy.json` - Policy fields
- `~/code/huf-memory/doctype_designs/memory_profile.json` - Profile fields
- `~/code/huf-memory/frontend/src/types/memory.types.ts` - Frontend types (already done)
- `~/code/huf-memory/frontend/src/services/memoryApi.ts` - API service (already done)
- `~/code/huf-memory/profiles/*/profile.json` - Profile definitions

## Deliverables

### 1. Agent Memory Tab Component
Create: `frontend/src/components/memory/AgentMemoryTab.tsx`

React component for Agent form Memory tab:
- Enable/disable memory toggle
- Memory Policy selector (with create new option)
- Memory Profile selector
- Capture owner selection (main_agent, memory_agent, post_run_llm, rules_only)
- Capture stage selection (in_prompt, post_response_sync, post_response_async)
- Default scope type selection
- Retrieval mode selection (inject, tool_only, hybrid)
- Token budget slider
- Max items input
- Advanced options accordion

Props:
```typescript
interface AgentMemoryTabProps {
  agentData: Agent;
  onChange: (field: string, value: any) => void;
}
```

### 2. Memory Policy Form Component
Create: `frontend/src/components/memory/MemoryPolicyForm.tsx`

Full form for creating/editing Memory Policy:
- Basic info (name, enabled)
- Capture configuration section
- Frequency settings with dynamic fields
- Schema section (JSON editor for capture schema)
- Merge/update behavior section
- Storage configuration (FTS, vector toggles)
- Retrieval settings

### 3. Memory Profile Selector
Create: `frontend/src/components/memory/MemoryProfileSelector.tsx`

Profile selection with preview:
- Dropdown of available profiles
- Category filter tabs
- Profile card with icon, description
- Schema preview
- "Create Custom" option

### 4. Memory Explorer Page
Create: `frontend/src/pages/MemoryExplorer.tsx`

Full desk page for browsing memories:
- Filter sidebar:
  - Scope type filter
  - Agent filter
  - Memory type filter
  - Profile filter
  - Date range picker
  - Status filter
- Main content:
  - Memory cards list/grid view toggle
  - Search bar with FTS
  - Sort options (date, relevance, importance)
  - Pagination
- Memory card component showing:
  - Title
  - Memory type badge
  - Scope info
  - Created date
  - Confidence score
  - Tags
  - Quick actions (view, edit, delete)

### 5. Memory Detail View
Create: `frontend/src/components/memory/MemoryDetailView.tsx`

Modal or slide-out panel:
- Full memory record display
- Formatted JSON data viewer
- Source info (agent, conversation, run links)
- Scope and visibility info
- Indexing status (FTS, vector)
- Retrieval stats
- Related memories
- Action buttons (edit, delete, supersede)

### 6. Memory Record Form
Create: `frontend/src/components/memory/MemoryRecordForm.tsx`

Form for manual memory creation/editing:
- Title input
- Agent selector
- Source type selector
- Memory type selector
- JSON data editor (with schema validation if profile selected)
- Summary text area
- Scope configuration
- Tags input
- Advanced: TTL, effective dates, supersede links

### 7. Conversation Memory Panel
Create: `frontend/src/components/memory/ConversationMemoryPanel.tsx`

Side panel for Agent Conversation:
- List of memories created in this conversation
- Quick capture button
- Memory stats (count, last capture)
- End conversation button with capture option
- Manual memory creation

### 8. Profile Cards
Create: `frontend/src/components/memory/ProfileCard.tsx`

Visual card for each profile type:
- Icon
- Profile name
- Category badge
- Description
- Key features list
- "Use Profile" button

### 9. Memory Search Component
Create: `frontend/src/components/memory/MemorySearch.tsx`

Reusable search component:
- Search input with suggestions
- Filter chips
- Scope selector
- Recent searches
- Search results preview

### 10. Additional Profile Implementations
Create 3 more opinionated profiles:

#### Science/Research Profile
Create: `profiles/science_research/profile.json`
Fields: concepts, claims, evidence_level, references, contradictions, open_questions

#### Language Learning Profile
Create: `profiles/language_learning/profile.json`
Fields: target_language, proficiency_level, vocabulary_learned, grammar_rules, practice_history

#### CRM/Customer Context Profile
Create: `profiles/crm_customer/profile.json`
Fields: customer_id, interaction_type, preferences, pain_points, next_actions, deal_stage

### 11. Desk Page Configuration
Create: `huf/huf/desk_page/memory_explorer/`
- `memory_explorer.json` - Desk page config
- Links from sidebar navigation

### 12. API Integration Hooks
Create: `frontend/src/components/memory/hooks/useMemorySearch.ts`
```typescript
export function useMemorySearch() {
  const search = async (query: string, filters: MemoryFilters) => {...}
  const recent = async (limit: number) => {...}
  const byScope = async (scopeType: string, scopeKey: string) => {...}
  return { search, recent, byScope, results, loading, error };
}
```

Create: `frontend/src/components/memory/hooks/useMemoryPolicy.ts`
```typescript
export function useMemoryPolicy(agentId?: string) {
  const getPolicy = async () => {...}
  const createPolicy = async (data: MemoryPolicy) => {...}
  const updatePolicy = async (id: string, data: Partial<MemoryPolicy>) => {...}
  return { policy, createPolicy, updatePolicy, loading };
}
```

## Routes to Add

Add to frontend routing:
- `/memory` - Memory Explorer main page
- `/memory/:id` - Memory detail view
- `/memory/policies` - Policy management
- `/memory/profiles` - Profile browser

## Commits Required
1. `feat(memory): implement Agent Memory tab UI component`
2. `feat(memory): implement Memory Explorer desk page`
3. `feat(memory): implement Memory Policy form components`
4. `feat(memory): implement Memory Record detail and form views`
5. `feat(memory): add Conversation memory panel`
6. `feat(memory): implement Science/Research, Language Learning, CRM profiles`
7. `feat(memory): add memory search and filter components`

## Success Criteria
- Agent form shows Memory tab with all configuration options
- Memory Explorer loads and displays records with filtering
- Can create/edit Memory Policies via UI
- Can manually create Memory Records
- Profile selector shows all 6 profiles with icons
- Search returns results with proper highlighting
- All components use existing TypeScript types and API services