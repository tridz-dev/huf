# HUF Flow UI - Master Index

> **Single point of reference for all Flow UI development work**

**Last Updated**: 2026-03-28  
**Active Branch**: `feature/flow-backend-integration`  
**Status**: Critical fixes in progress

---

## 📚 Documentation Index

### Primary Trackers (Active Work)

| Document | Purpose | Last Updated |
|----------|---------|--------------|
| **[FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md)** | NodeSelectionModal status, triggers, actions, known issues | 2026-03-28 |
| **[FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md)** | Overall Flow UI status, backend integration, canvas features | 2026-03-28 |
| **[INDEX.md](INDEX.md)** | This file - master navigation index | 2026-03-28 |

### Architecture & Design

| Document | Location | Purpose |
|----------|----------|---------|
| **[AGENTS.md](AGENTS.md)** | Root | Main project documentation for AI agents |
| **[CLAUDE.md](CLAUDE.md)** | Root | Claude-specific context and guidelines |
| **[frontend/docs/ARCHITECTURE.md](frontend/docs/ARCHITECTURE.md)** | Frontend | Frontend architecture overview |
| **[frontend/docs/DASHBOARD_FRAMEWORK.md](frontend/docs/DASHBOARD_FRAMEWORK.md)** | Frontend | Dashboard component framework |
| **[frontend/docs/REFACTORING_PROPOSAL.md](frontend/docs/REFACTORING_PROPOSAL.md)** | Frontend | Proposed refactoring plans |

### Feature Documentation

| Document | Location | Purpose |
|----------|----------|---------|
| **[frontend/docs/FEATURES.md](frontend/docs/FEATURES.md)** | Frontend | Feature implementation guide |
| **[frontend/docs/IMPLEMENTATION_SUMMARY.md](frontend/docs/IMPLEMENTATION_SUMMARY.md)** | Frontend | Implementation summary |
| **[frontend/docs/QUICK_START.md](frontend/docs/QUICK_START.md)** | Frontend | Quick start guide |
| **[frontend/docs/CONTRIBUTE.md](frontend/docs/CONTRIBUTE.md)** | Frontend | Contribution guidelines |

### Backend Documentation

| Document | Location | Purpose |
|----------|----------|---------|
| **[docs/FLOW_ENGINE_FEATURE_GUIDE.md](docs/FLOW_ENGINE_FEATURE_GUIDE.md)** | docs/ | Flow engine backend feature guide |

---

## 🔴 Critical Issues

### BUG-001: Actions Tab Crash
- **Error**: React Error #130 (Element type is invalid)
- **Status**: 🔴 **OPEN**
- **Impact**: Complete UI crash (white screen)
- **Details**: [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) → Issues → Issue #1
- **File**: `frontend/src/components/modals/NodeSelectionModal.tsx`

### BUG-002: Infinite Loop
- **Error**: React Error #185 (Maximum update depth exceeded)
- **Status**: 🔴 **OPEN**
- **Impact**: Browser freeze on Flows page
- **Details**: [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) → Bugs
- **Files**: `FlowContext.tsx`, `FlowCanvas.tsx`, `usePageData.ts`

### BUG-003: DocType No Auto-Suggestion
- **Error**: Document Type field shows plain text input
- **Status**: 🟡 **NEW**
- **Impact**: Poor UX - no auto-complete for DocType selection
- **Details**: See below
- **Comparison**: Agent form has Combobox with `getDocTypes()` API

---

## 🎯 Active Work Items

### Missing Features (High Priority)

| Feature | Current State | Expected | Files |
|---------|--------------|----------|-------|
| **DocType Auto-Suggestion** | Plain text input | Combobox with search | `NodeSelectionModal.tsx` |
| **Run Agent Config** | No form | Agent selector, prompt template | `NodeSelectionModal.tsx`, `RightSidebar.tsx` |
| **Call Tool Config** | No form | Tool selector, params mapping | `NodeSelectionModal.tsx`, `RightSidebar.tsx` |
| **LLM Router Config** | No form | Branch builder, condition editor | `NodeSelectionModal.tsx`, `RightSidebar.tsx` |
| **Human Approval Config** | No form | Approver select, timeout | `NodeSelectionModal.tsx`, `RightSidebar.tsx` |

### Implementation References

#### How DocType Auto-Suggestion Works (Agent Form)
```
AgentFormPage.tsx
  → Uses: Combobox from @/components/ui/combobox
  → Fetches: getDocTypes() from agentApi.ts
  → Renders: TriggerFieldsRenderer.tsx (lines 65-94)
```

#### Required for Flow Modal
```
NodeSelectionModal.tsx
  → Needs: Combobox import
  → Needs: getDocTypes() call
  → Needs: State for docTypes, loadingDocTypes
  → Update: renderTriggerForm() for doc-event type
```

---

## 📁 Key Files

### Frontend Components

| Component | Path | Purpose |
|-----------|------|---------|
| **NodeSelectionModal** | `frontend/src/components/modals/NodeSelectionModal.tsx` | Main modal for triggers/actions |
| **RightSidebar** | `frontend/src/components/RightSidebar.tsx` | Node configuration panel |
| **FlowCanvas** | `frontend/src/components/FlowCanvas.tsx` | React Flow canvas |
| **FlowContext** | `frontend/src/contexts/FlowContext.tsx` | State management |
| **flowService** | `frontend/src/services/flowService.ts` | Business logic |
| **flowApi** | `frontend/src/services/flowApi.ts` | Backend API calls |
| **flowSerializer** | `frontend/src/services/flowSerializer.ts` | Data transformation |

### Data Definitions

| File | Path | Purpose |
|------|------|---------|
| **triggers.ts** | `frontend/src/data/triggers.ts` | Trigger definitions |
| **actions.ts** | `frontend/src/data/actions.ts` | Action definitions |
| **flow.types.ts** | `frontend/src/types/flow.types.ts` | TypeScript types |

### Reference Implementations

| Component | Path | Purpose |
|-----------|------|---------|
| **TriggerFieldsRenderer** | `frontend/src/components/agent/TriggerFieldsRenderer.tsx` | Reference for DocType Combobox |
| **Combobox** | `frontend/src/components/ui/combobox.tsx` | Reusable combobox component |
| **AgentFormPage** | `frontend/src/pages/AgentFormPage.tsx` | Reference for getDocTypes() usage |

---

## 🧪 Test Files

| File | Purpose |
|------|---------|
| `test_backend_core.py` | Backend API tests |
| `test_authenticated_flows.py` | Authenticated flow tests |
| `screenshots/` | Visual test evidence |

---

## 📊 Status Summary

| Category | Working | Partial | Broken | Missing |
|----------|---------|---------|--------|---------|
| **Bugs** | 3 | 0 | 3 | 0 |
| **Triggers** | 1 | 3 | 0 | 7 |
| **Actions** | 0 | 0 | 14 | 0 |
| **Config Forms** | 0 | 1 | 0 | 6 |
| **Backend APIs** | 7 | 0 | 0 | 0 |

**Overall**: ~35% Complete

---

## 🚀 Quick Actions

### For Bug Fixes
1. Check [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) for detailed bug info
2. Check [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) for system-wide status

### For New Features
1. Check **Implementation References** above for similar working code
2. Check **Key Files** for where to make changes

### For Testing
1. Check `screenshots/` folder for visual evidence
2. Run `test_backend_core.py` for API tests
3. Use browser console to check for React errors

---

## 📝 Update Log

| Date | Change | Commit |
|------|--------|--------|
| 2026-03-28 | Created INDEX.md | - |
| 2026-03-28 | Added DocType issue to trackers | - |
| 2026-03-27 | Fixed icon imports and safety checks | c03eaf8 |
| 2026-03-27 | Created feature trackers | c03eaf8 |
| 2026-03-27 | Initial Flow UI fixes | 102fb29 |

---

## 🔗 Quick Links

- **Backend API Docs**: See AGENTS.md → Flow Engine section
- **Frontend Architecture**: See frontend/docs/ARCHITECTURE.md
- **Dashboard Framework**: See frontend/docs/DASHBOARD_FRAMEWORK.md
- **Component Reference**: See frontend/docs/FEATURES.md

---

*This index is the single source of truth. Update it when adding new documents or completing major milestones.*
