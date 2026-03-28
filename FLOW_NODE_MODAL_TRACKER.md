# Flow Node Modal - Feature Implementation Tracker

> **Component**: `NodeSelectionModal.tsx`  
> **Last Updated**: 2026-03-27  
> **Branch**: `feature/flow-backend-integration`

---

## 🎯 Overview

The NodeSelectionModal is the primary interface for adding/configuring nodes in the Flow Canvas. It has two main tabs:
1. **Triggers** - Entry points for flows
2. **Actions** - Processing nodes

**Current Status**: 🟡 **Partially Working** - Triggers tab functional, Actions tab crashes (React Error #130)

---

## 📑 Tabs Structure

```
┌─────────────────────────────────────────┐
│  Select Trigger / Add Action        [X] │
├─────────────────────────────────────────┤
│  [Triggers] [Actions]                   │ ← Main Tabs
├─────────────────────────────────────────┤
│                                         │
│  Triggers Tab:                          │
│  ┌─────────┬─────────┬─────────┬──────┐ │
│  │Explore  │AI &     │Apps     │Utility│ │ ← Sub-tabs
│  │         │Agents   │         │       │ │
│  └─────────┴─────────┴─────────┴──────┘ │
│                                         │
│  Actions Tab:                           │
│  ┌────────────────────────────────────┐ │
│  │ AI & Agents                        │ │ ← Categories
│  │ Tools                              │ │
│  │ Control Flow                       │ │
│  │ Transform                          │ │
│  │ Utilities                          │ │
│  │ Integrations                       │ │
│  └────────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🔥 TRIGGERS TAB

### Sub-Tab: Explore

| Trigger | Icon | Status | Backend Support | Config Form | Notes |
|---------|------|--------|-----------------|-------------|-------|
| Webhook | Webhook | ✅ **Working** | ✅ `trigger.webhook` | 🟡 Basic | URL, Method, API Key fields |
| Schedule | Clock | ✅ **Working** | ❌ No | 🟡 Basic | Interval, Cron fields |
| Human Input | UserCheck | ✅ **Working** | ❌ No | 🔴 None | Placeholder - no config |
| Data | Database | ✅ **Working** | ❌ No | 🟡 Basic | DocType, Event fields |

**Test Results**:
- ✅ Tab opens without errors
- ✅ All triggers display with icons
- ✅ Clicking trigger highlights selection
- ✅ Config form appears for selected trigger
- ⚠️ "Save Configuration" button works

---

### Sub-Tab: AI & Agents

| Feature | Status | Notes |
|---------|--------|-------|
| Agent List Loading | ✅ **Working** | Fetches from `getAgents()` API |
| Agent Cards Display | ✅ **Working** | Shows name, status, instructions |
| Agent Selection | ✅ **Working** | Highlights selected agent |
| Config on Select | ⚠️ **Partial** | Creates `app-trigger` type (should be direct agent trigger) |

**Issues**:
- Agent selection creates `type: 'app-trigger'` with integration 'agent'
- Should ideally create a dedicated agent trigger type

---

### Sub-Tab: Apps

| App | Icon | Status | Config Available | Notes |
|-----|------|--------|------------------|-------|
| Google Sheets | Sheet | ✅ **UI Only** | 🔴 None | Placeholder - no backend |
| Slack | MessageSquare | ✅ **UI Only** | 🔴 None | Placeholder - no backend |
| Notion | FileText | ✅ **UI Only** | 🔴 None | Placeholder - no backend |
| Gmail | Mail | ✅ **UI Only** | 🔴 None | Placeholder - no backend |
| HubSpot | Database | ✅ **UI Only** | 🔴 None | Placeholder - no backend |
| Calendar | Calendar | ✅ **UI Only** | 🔴 None | Placeholder - no backend |

**Status**: All apps are UI placeholders. No backend implementation yet.

---

### Sub-Tab: Utility

| Status | Notes |
|--------|-------|
| 🔴 **Empty** | No utility triggers defined in `triggers.ts` |

**Missing**: Utility-specific triggers (HTTP polling, webhook catch, etc.)

---

## ⚡ ACTIONS TAB

### Category: AI & Agents

| Action | Icon | Backend Type | Status | Config Form | Tested |
|--------|------|--------------|--------|-------------|--------|
| Run Agent | Bot | `agent.run` | 🔴 **Crashes** | 🔴 Missing | ❌ No |
| Call Tool | Wrench | `tool.call` | 🔴 **Crashes** | 🔴 Missing | ❌ No |

**Issue**: Actions tab crashes with React Error #130 when opened

**Error Details**:
```
Error: Minified React error #130
Element type is invalid: expected string/class/function but got: undefined
```

**Root Cause Investigation**:
1. ✅ Icons imported from lucide-react (Bot, Wrench)
2. ✅ Icons added to iconMap
3. ✅ Icon safety checks added to renderActionCategory
4. ❌ Still crashes - suspect action config or category filtering

**Next Steps**:
- [ ] Debug action filtering (agentActions, toolActions)
- [ ] Check if any action has null/undefined icon property
- [ ] Verify category strings match between actions.ts and NodeSelectionModal

---

### Category: Tools

| Action | Icon | Status | Notes |
|--------|------|--------|-------|
| Call Tool | Wrench | 🔴 **Crashes** | Same as above |

**Note**: Tools category only has "Call Tool" action currently.

---

### Category: Control Flow

| Action | Icon | Backend Type | Status | Config Form | Tested |
|--------|------|--------------|--------|-------------|--------|
| LLM Router | GitBranch | `router.llm` | 🔴 **Crashes** | 🔴 Missing | ❌ No |
| Human Approval | UserCheck | `human.approval` | 🔴 **Crashes** | 🔴 Missing | ❌ No |
| Loop | RotateCw | - | 🔴 **Crashes** | 🔴 Missing | ❌ No |

**Status**: All control flow actions cause crash when Actions tab opened.

---

### Category: Transform

| Action | Icon | Status | Config Form | Notes |
|--------|------|--------|-------------|-------|
| Transform Data | Repeat | 🔴 **Crashes** | 🔴 Missing | Frontend only - no backend |
| Execute Code | Code | 🔴 **Crashes** | 🔴 Missing | Frontend only - no backend |

---

### Category: Utilities

| Action | Icon | Status | Config Form | Notes |
|--------|------|--------|-------------|-------|
| Send Email | Mail | 🔴 **Crashes** | 🔴 Missing | Frontend only |
| Call Webhook | Webhook | 🔴 **Crashes** | 🔴 Missing | Frontend only |
| File Operations | FileText | 🔴 **Crashes** | 🔴 Missing | Frontend only |
| Date Utility | Calendar | 🔴 **Crashes** | 🔴 Missing | Frontend only |

---

### Category: Integrations

| Action | Icon | Status | Config Form | Notes |
|--------|------|--------|-------------|-------|
| Slack | MessageSquare | 🔴 **Crashes** | 🔴 Missing | Placeholder |
| Google Sheets | Sheet | 🔴 **Crashes** | 🔴 Missing | Placeholder |
| Notion | FileText | 🔴 **Crashes** | 🔴 Missing | Placeholder |

---

## 🐛 Known Issues

### Issue #1: Actions Tab Crash (CRITICAL)
- **ID**: MODAL-001
- **Severity**: 🔴 Critical
- **Status**: Open
- **Error**: React Error #130
- **Trigger**: Clicking "Actions" tab
- **Impact**: Complete UI crash - white screen

**Debug Log**:
```
✅ Icons imported from lucide-react
✅ Icons in iconMap: Bot, Wrench, GitBranch, UserCheck, etc.
✅ Safety checks added for undefined icons
✅ Categories filtered: agentActions, toolActions, etc.
❌ Still crashes

Suspected causes:
- Action in actions.ts has icon property set to undefined/null
- Category mismatch between actions.ts and filter in NodeSelectionModal
- renderActionCategory called with actions containing invalid items
```

**Fix Attempts**:
| Attempt | Date | Result |
|---------|------|--------|
| Add icon imports | 2026-03-27 | ❌ No change |
| Fix iconMap mappings | 2026-03-27 | ❌ No change |
| Add Icon null checks | 2026-03-27 | ❌ No change |
| Add category filters | 2026-03-27 | ❌ No change |

**Next Fix Attempts**:
- [ ] Log all actions to console to verify icon property
- [ ] Check if any action has icon: undefined
- [ ] Verify all actions in actions.ts have valid icon strings
- [ ] Add try-catch around renderActionCategory

---

### Issue #2: Missing Config Forms
- **ID**: MODAL-002
- **Severity**: 🟡 Medium
- **Status**: Open

**Actions needing config forms**:
1. Run Agent - needs agent selector, prompt template
2. Call Tool - needs tool selector, parameter mapping
3. LLM Router - needs branch builder, condition editor
4. Human Approval - needs approver selection, timeout
5. All utility actions - need their specific configs

---

### Issue #3: Frontend-Only Actions
- **ID**: MODAL-003
- **Severity**: 🟡 Medium
- **Status**: Expected (v0.2+)

**Actions not in backend v0.1**:
- Transform Data
- Loop
- Execute Code
- Send Email
- Call Webhook
- File Operations
- Date Utility

**Solution**: Mark with "Beta" badge (already implemented)

---

## ✅ Working Features

### Fully Functional
1. ✅ Modal opens when clicking unconfigured trigger node
2. ✅ Modal opens when clicking "+" button on node
3. ✅ Triggers tab displays correctly
4. ✅ All trigger sub-tabs work (Explore, AI & Agents, Apps, Utility)
5. ✅ Trigger icons render correctly
6. ✅ Trigger selection highlights correctly
7. ✅ Trigger config forms show for: Webhook, Schedule, Doc Event
8. ✅ Agent list loads and displays
9. ✅ Cancel button closes modal
10. ✅ Save Configuration button works for triggers

---

## 📋 Testing Checklist

### Triggers Tab Test
- [x] Open modal on trigger click
- [x] Switch between sub-tabs
- [x] Select webhook trigger
- [x] Configure webhook URL
- [x] Save configuration
- [x] Load AI & Agents list
- [x] Select agent trigger
- [x] View Apps tab

### Actions Tab Test
- [ ] Open Actions tab (CRASHES - BLOCKED)
- [ ] View AI & Agents category
- [ ] View Tools category
- [ ] Select Run Agent action
- [ ] Configure Run Agent
- [ ] Select Call Tool action
- [ ] Configure Call Tool
- [ ] Select LLM Router
- [ ] Configure branches

---

## 🔧 Implementation Details

### File Structure
```
frontend/src/components/modals/
├── NodeSelectionModal.tsx     ← Main component
├── TriggerConfigModal.tsx     ← Unused?
└── ActionSelectionModal.tsx   ← Unused (dead code)
```

### Data Sources
```
frontend/src/data/
├── triggers.ts    ← Trigger definitions
└── actions.ts     ← Action definitions
```

### Icon Mapping
```typescript
// iconMap in NodeSelectionModal.tsx
{
  Webhook, Clock, Mail, MessageSquare, FileText,
  Calendar, Database, Sheet, Repeat, GitBranch,
  RotateCw, Code, UserCheck, Bot, Wrench
}
```

### Category Filtering
```typescript
// Actions tab categories
agentActions        → category === 'agent'
toolActions         → category === 'tool'
transformActions    → category === 'transform'
controlActions      → category === 'control'
utilityActions      → category === 'utility'
integrationActions  → category === 'integration'
```

---

## 🎯 Action Items

### Immediate (P0)
1. [ ] **Fix Actions tab crash** - Debug and fix React Error #130
2. [ ] **Add console logging** - Log all actions to identify undefined icon
3. [ ] **Test each action** - Verify all actions have valid icon property

### Short Term (P1)
4. [ ] **Create Run Agent config form**
5. [ ] **Create Call Tool config form**
6. [ ] **Create LLM Router config form**
7. [ ] **Create Human Approval config form**

### Medium Term (P2)
8. [ ] **Add advanced trigger configs** (headers, timezone, etc.)
9. [ ] **Add validation to config forms**
10. [ ] **Add search/filter to actions**

---

## 📸 Screenshots

| View | File | Status |
|------|------|--------|
| Triggers Tab | `screenshots/before_actions.png` | ✅ Working |
| Actions Tab | `screenshots/after_actions.png` | 🔴 White screen |

---

## 📝 Change Log

| Date | Change | Commit |
|------|--------|--------|
| 2026-03-27 | Added UserCheck, Wrench imports | 102fb29 |
| 2026-03-27 | Fixed iconMap mappings | 102fb29 |
| 2026-03-27 | Added icon safety checks | 102fb29 |
| 2026-03-27 | Added agent/tool categories | 102fb29 |
| 2026-03-27 | Added agent.run, tool.call actions | 102fb29 |

---

## 🔗 Related Files

| File | Purpose |
|------|---------|
| `frontend/src/components/modals/NodeSelectionModal.tsx` | Main modal component |
| `frontend/src/data/triggers.ts` | Trigger definitions |
| `frontend/src/data/actions.ts` | Action definitions |
| `frontend/src/types/modal.types.ts` | TypeScript types |
| `frontend/src/types/flow.types.ts` | Flow node types |

---

*Update this tracker after each test/fix session.*
