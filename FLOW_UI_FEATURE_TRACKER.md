# Flow UI Feature Tracker

> Last Updated: 2026-03-27  
> Branch: `feature/flow-backend-integration`  
> Status: Critical Fixes In Progress

---

## 🐛 Critical Bugs

| Bug ID | Issue | Error | Status | Notes | Fixed In |
|--------|-------|-------|--------|-------|----------|
| BUG-001 | Action tab crash | React #130 | 🔴 **OPEN** | White screen when clicking Actions tab | - |
| BUG-002 | Node click infinite loop | React #185 | 🟡 **PARTIAL** | Still occurs on Flows page load | - |
| BUG-003 | Missing icon imports | React #130 | 🟢 **FIXED** | UserCheck, Wrench added | commit 102fb29 |
| BUG-004 | RightSidebar useState typo | - | 🟢 **FIXED** | Changed to useEffect | commit 102fb29 |
| BUG-005 | usePageData infinite loop | - | 🟢 **FIXED** | Compare length vs reference | commit 102fb29 |

### Bug Details

#### BUG-001: Action Tab Crash (React Error #130)
- **Error**: `Element type is invalid: expected a string or class/function but got: undefined`
- **Trigger**: Clicking "Actions" tab in NodeSelectionModal
- **Root Cause**: Icon component undefined in iconMap
- **Fix Attempts**:
  1. ✅ Added UserCheck, Wrench imports
  2. ✅ Fixed iconMap mappings (UserCheck: Clock → UserCheck)
  3. ✅ Added null safety checks for Icon rendering
  4. ❌ Still crashing - need to investigate further
- **Next Steps**: Check if actions.ts has icons not in iconMap

#### BUG-002: Infinite Loop (React Error #185)
- **Error**: `Maximum update depth exceeded`
- **Trigger**: Loading Flows page, clicking nodes
- **Root Cause**: Circular state updates between FlowContext and components
- **Fix Attempts**:
  1. ✅ Removed loadActiveFlow from update callbacks
  2. ✅ Added isSyncingFromProps guard in FlowCanvas
  3. ✅ Fixed usePageData comparison
  4. ❌ Still occurs - need deeper refactor
- **Next Steps**: Implement single source of truth pattern

---

## 🎯 Triggers

| Trigger | Icon | Backend Type | Frontend Status | Backend Status | Tested | Notes |
|---------|------|--------------|-----------------|----------------|--------|-------|
| Webhook | Webhook | `trigger.webhook` | ✅ Implemented | ✅ Implemented | ✅ | Working |
| Schedule | Clock | - | ✅ Implemented | ❌ Not in v0.1 | ⚠️ | Frontend only |
| Doc Event | Database | - | ✅ Implemented | ❌ Not in v0.1 | ⚠️ | Frontend only |
| App Trigger | Mail | - | ✅ Implemented | ❌ Not in v0.1 | ⚠️ | Needs integration |
| Human Input | UserCheck | - | ✅ Implemented | ❌ Not in v0.1 | ⚠️ | Frontend only |
| Gmail | Mail | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |
| Slack | MessageSquare | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |
| Notion | FileText | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |
| Google Sheets | Sheet | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |
| HubSpot | Database | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |
| Calendar | Calendar | - | ✅ UI Only | ❌ Not implemented | ❌ | Placeholder |

### Trigger Configuration Forms

| Trigger | Basic Config | Advanced Config | Validation | Status |
|---------|--------------|-----------------|------------|--------|
| Webhook | URL, Method, API Key | Headers, Body Template | ❌ | 🟡 Partial |
| Schedule | Interval, Cron | Timezone, Start/End Date | ❌ | 🟡 Partial |
| Doc Event | DocType, Event | Condition Filter | ❌ | 🟡 Partial |
| App Trigger | Integration, Event | App-specific config | ❌ | 🔴 Missing |

---

## ⚡ Actions

| Action | Icon | Category | Backend Type | Frontend Status | Backend Status | Tested | Notes |
|--------|------|----------|--------------|-----------------|----------------|--------|-------|
| Run Agent | Bot | agent | `agent.run` | ✅ Implemented | ✅ Implemented | ⚠️ | Added, needs config form |
| Call Tool | Wrench | tool | `tool.call` | ✅ Implemented | ✅ Implemented | ⚠️ | Added, needs config form |
| LLM Router | GitBranch | control | `router.llm` | ✅ UI | ✅ Implemented | ⚠️ | Frontend type mismatch |
| Human Approval | UserCheck | control | `human.approval` | ✅ UI | ✅ Implemented | ⚠️ | Needs config form |
| Transform Data | Repeat | transform | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Loop | RotateCw | control | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Execute Code | Code | transform | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Send Email | Mail | utility | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Call Webhook | Webhook | utility | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| File Operations | FileText | utility | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Date Utility | Calendar | utility | - | ✅ UI | ❌ Not in v0.1 | ❌ | Frontend only |
| Slack | MessageSquare | integration | - | ✅ UI | ❌ Not implemented | ❌ | Placeholder |
| Google Sheets | Sheet | integration | - | ✅ UI | ❌ Not implemented | ❌ | Placeholder |
| Notion | FileText | integration | - | ✅ UI | ❌ Not implemented | ❌ | Placeholder |

### Action Configuration Forms

| Action | Basic Config | Advanced Config | Validation | Status |
|--------|--------------|-----------------|------------|--------|
| Run Agent | Agent select | Prompt template, Context mapping | ❌ | 🔴 Missing |
| Call Tool | Tool select | Parameter mapping | ❌ | 🔴 Missing |
| LLM Router | Branches | Condition builder | ❌ | 🔴 Missing |
| Human Approval | Approvers | Timeout, Message | ❌ | 🔴 Missing |
| Transform Data | Field mapping | Operations | ❌ | 🔴 Missing |
| Loop | Max iterations | Iteration config | ❌ | 🔴 Missing |
| Code | Language, Code | - | ❌ | 🔴 Missing |

---

## 🎨 Node Types

| Node Type | Visual | Selection | Config Panel | Drag/Drop | Connect | Status |
|-----------|--------|-----------|--------------|-----------|---------|--------|
| Trigger | ✅ | ✅ | 🟡 Partial | ✅ | ✅ | Working |
| Action | ✅ | ✅ | 🔴 Missing | ✅ | ✅ | Needs config forms |
| End | ✅ | ✅ | N/A | ✅ | ✅ | Working |

---

## 📋 Modals

| Modal | Open | Close | Save | Validation | Status | Notes |
|-------|------|-------|------|------------|--------|-------|
| NodeSelectionModal | ✅ | ✅ | ✅ | ❌ | 🟡 Partial | Action tab crashes |
| TriggerConfigModal | ✅ | ✅ | ✅ | ❌ | 🟡 Partial | Needs advanced options |
| ActionSelectionModal | - | - | - | - | 🔴 Not Used | Dead code? |
| FlowSettingsModal | 🔴 | 🔴 | 🔴 | 🔴 | **MISSING** | Not implemented |

---

## 🔧 Settings & Features

| Feature | UI | Backend | Integration | Status | Notes |
|---------|----|---------|-------------|--------|-------|
| Flow Name Edit | ✅ | ✅ | ✅ | Working | |
| Flow Description | ✅ | ❌ | ❌ | Frontend only | Not in backend |
| Flow Category | ✅ | ❌ | ❌ | Frontend only | Not in backend |
| Flow Status | ✅ | ✅ | ⚠️ | Mismatch | Frontend: draft/active/paused/error, Backend: Draft/Active/Archived |
| Flow Version | Read-only | Auto | ✅ | Working | |
| Execution Mode | ❌ | ✅ | ❌ | Missing | Normal vs Agentic |
| Max Hops | ❌ | ✅ | ❌ | Missing | Default 100 |
| Auto-save | ❌ | ❌ | ❌ | Not implemented | |
| Undo/Redo | ❌ | ❌ | ❌ | Not implemented | |
| Copy/Paste | ❌ | ❌ | ❌ | Not implemented | |
| Import/Export | ❌ | ❌ | ❌ | Not implemented | |

---

## 🔄 Backend Integration

| Feature | API Endpoint | Frontend Service | Serializer | Status |
|---------|--------------|------------------|------------|--------|
| Get Flow Definition | ✅ `get_flow_definition` | ✅ | ✅ | Working |
| Save Flow Definition | ✅ `save_flow_definition` | ✅ | ✅ | Working |
| Run Flow | ✅ `run_flow` | ✅ | N/A | Working |
| Get Flow Run | ✅ `get_flow_run` | ✅ | N/A | Working |
| List Flow Runs | ✅ `list_flow_runs` | ✅ | N/A | Working |
| Approve Flow Run | ✅ `approve_flow_run` | ✅ | N/A | Working |
| Reject Flow Run | ✅ `reject_flow_run` | ✅ | N/A | Working |

---

## 📱 Canvas Features

| Feature | Implementation | Status | Notes |
|---------|----------------|--------|-------|
| Node Drag | React Flow | ✅ Working | |
| Node Select | React Flow | ✅ Working | |
| Edge Connect | React Flow | ✅ Working | |
| Edge Delete | React Flow | ✅ Working | |
| Pan/Zoom | React Flow | ✅ Working | |
| MiniMap | React Flow | ✅ Working | |
| Controls | React Flow | ✅ Working | |
| Grid Background | React Flow | ✅ Working | |
| Add Node Button | Custom | ✅ Working | |
| Delete Node | Custom | ✅ Working | |
| Right Sidebar | Custom | 🟡 Partial | Needs config forms |
| Left Sidebar | Custom | ✅ Working | |

---

## ✅ Test Status

| Test | Date | Result | Notes |
|------|------|--------|-------|
| Backend API | 2026-03-27 | ✅ Pass | All endpoints working |
| Multi-node flow | 2026-03-27 | ✅ Pass | 3 nodes + 2 edges display |
| Flow execution | 2026-03-27 | ✅ Pass | Run completes successfully |
| Node selection | 2026-03-27 | 🔴 Fail | Action tab crashes |
| Node configuration | 2026-03-27 | 🟡 Partial | Only trigger has basic form |
| Save flow | 2026-03-27 | 🟡 Partial | In-memory only |
| Load flow | 2026-03-27 | ✅ Pass | From backend working |

---

## 📝 Remaining Tasks (Priority Order)

### P0 - Critical (Blocks Usage)
1. [ ] **Fix Action tab crash** (BUG-001)
2. [ ] **Fix infinite loop** (BUG-002)
3. [ ] **Create FlowSettingsModal** - Flow metadata editing

### P1 - High (Core Features)
4. [ ] **agent.run config form** - Agent selector, prompt template
5. [ ] **tool.call config form** - Tool selector, parameter mapping
6. [ ] **router.llm config form** - Branch builder, condition editor
7. [ ] **human.approval config form** - Approver selection, timeout
8. [ ] **Align status values** - Frontend/backend consistency

### P2 - Medium (UX Improvements)
9. [ ] **Advanced trigger configs** - Headers, timezone, filters
10. [ ] **Node validation** - Required fields, error messages
11. [ ] **Auto-save** - Debounced persistence
12. [ ] **Undo/Redo** - Action history

### P3 - Low (Nice to Have)
13. [ ] **Copy/Paste nodes** - Clipboard integration
14. [ ] **Import/Export** - JSON format
15. [ ] **Version history** - Restore previous versions
16. [ ] **Keyboard shortcuts** - Power user features

---

## 🔍 Debug Notes

### Current Issues Being Investigated

**Action Tab Crash:**
- Icons verified: Bot, Wrench, GitBranch, UserCheck all in iconMap
- Imports verified: All icons imported from lucide-react
- Safety checks added: Icon rendering has null checks
- Still crashing → Need to check if any action has undefined/null icon

**Infinite Loop:**
- FlowContext updated to not call loadActiveFlow in callbacks
- FlowCanvas has isSyncingFromProps guard
- usePageData compares length vs reference
- Still happening → Need to check FlowsSidebarContent or other subscribers

---

## 📊 Summary Statistics

| Category | Total | Working | Partial | Broken | Missing |
|----------|-------|---------|---------|--------|---------|
| Bugs | 5 | 3 | 0 | 2 | 0 |
| Triggers | 11 | 1 | 3 | 0 | 7 |
| Actions | 14 | 2 | 2 | 0 | 10 |
| Modals | 4 | 0 | 2 | 0 | 2 |
| Settings | 10 | 4 | 1 | 0 | 5 |
| Canvas | 11 | 10 | 1 | 0 | 0 |
| Backend APIs | 7 | 7 | 0 | 0 | 0 |

**Overall Completion: ~45%**

---

## 🏷️ Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Working/Complete |
| 🟡 | Partial/Needs Work |
| 🔴 | Broken/Missing |
| ⚠️ | Caution/Issue |
| - | Not Applicable |

---

*This document should be updated after each testing/fixing session.*
