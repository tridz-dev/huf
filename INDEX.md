# HUF Flow UI - Master Index

> **Single point of reference for all Flow UI development work**

**Last Updated**: 2026-03-28  
**Active Branch**: `feature/flow-backend-integration`  
**Status**: Critical fixes in progress

---

## 🚀 Quick Start

| Task | Command/Info |
|------|--------------|
| **Start Docker** | `cd docker && docker compose up` |
| **Bench in devcontainer** | `cd /workspace/development/edge16 && bench start` — app at `apps/huf`; sync host edits via git push/pull ([DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) Option 4) |
| **Access App** | http://localhost:8000 (admin/admin) |
| **Frontend Dev** | `cd frontend && yarn dev` (port 8080) |
| **Build Frontend** | `cd frontend && yarn build` |
| **Run Tests** | `python test_backend_core.py` |

📖 **Full Environment Guide**: [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)

---

## 🔴 Critical Issues (Being Fixed)

| Issue | Error | Status | Tracker |
|-------|-------|--------|---------|
| Actions Tab Crash | React #130 | 🔴 Open | [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) |
| Infinite Loop | React #185 | 🟡 Partial | [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) |
| DocType field UX | Plain text | 🟡 Open | Below (BUG-003) |

---

## What we know

Facts to anchor debugging (verify after any fix with `yarn dev` + Flows page).

| ID | Symptom | Likely cause | Where |
|----|---------|--------------|--------|
| **BUG-001** | White screen / React **#130** when opening **Actions** tab | Invalid React element: **undefined component** (often wrong or missing **icon** in `iconMap`) | [`NodeSelectionModal.tsx`](frontend/src/components/modals/NodeSelectionModal.tsx) `iconMap`, [`actions.ts`](frontend/src/data/actions.ts) |
| **BUG-001 (data)** | Run Agent / Call Tool appear under **Transform**; **AI & Agents** / **Tools** sections empty | **`actions.ts` categories** use `'transform'` for those two actions, but the modal filters **`agent`** and **`tool`** buckets separately — buckets stay empty | [`NodeSelectionModal.tsx`](frontend/src/components/modals/NodeSelectionModal.tsx) `agentActions` / `toolActions` vs [`actions.ts`](frontend/src/data/actions.ts) `category` |
| **BUG-002** | React **#185** (max update depth) on Flows load / node click | **Circular or unstable state**: parent props ↔ `FlowContext` ↔ canvas, or `useEffect` deps that keep firing | [`FlowContext.tsx`](frontend/src/contexts/FlowContext.tsx), [`FlowCanvas.tsx`](frontend/src/components/FlowCanvas.tsx), [`usePageData.ts`](frontend/src/hooks/usePageData.ts) |
| **BUG-003** | Doc Event trigger: DocType is free text | No combobox; agent flow already has pattern | [`NodeSelectionModal.tsx`](frontend/src/components/modals/NodeSelectionModal.tsx) `doc-event` form; reference [`TriggerFieldsRenderer.tsx`](frontend/src/components/agent/TriggerFieldsRenderer.tsx) + `getDocTypes()` |

**Environment**: Backend APIs for core flow types are largely OK; problems are mostly **frontend state and UI**. See [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) for host vs Docker bench and git sync.

---

## Fix plan (do in order)

1. **Unblock Actions tab (BUG-001)**  
   - Reproduce with **dev build** (not only minified prod) to get the real component name in the stack.  
   - **Audit**: every `action.icon` / `trigger.icon` string must resolve in `iconMap` (or use a typed map + fallback).  
   - **Align data**: set `category` in [`actions.ts`](frontend/src/data/actions.ts) to match modal sections (`agent`, `tool`, `control`, `transform`, …) so filtering matches product intent (Run Agent → AI & Agents, Call Tool → Tools).  
   - Confirm Actions tab renders all categories without #130; add a short manual checklist to the modal tracker when done.

2. **Stop update loops (BUG-002)**  
   - Trace **who sets** `nodes` / `edges` / `activeFlow` and **who listens** (props vs context).  
   - Goal: **one direction of truth** (e.g. page owns server data, context owns editor draft, or the reverse — but not both rewriting each other every render).  
   - Stabilize callbacks (`useCallback`) and **narrow `useEffect` deps**; avoid `loadActiveFlow`-style calls inside effects that depend on the same state they update.  
   - Verify: open Flows, click nodes, no #185 in console.

3. **DocType combobox (BUG-003)**  
   - Mirror agent form: `Combobox` + `getDocTypes()` in doc-event config in `NodeSelectionModal` (loading + empty states).

4. **Config forms for backend-supported nodes**  
   - Run Agent, Call Tool, LLM Router, Human Approval in modal + [`RightSidebar.tsx`](frontend/src/components/RightSidebar.tsx) per [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md).

5. **Trackers**  
   - Update [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) and [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) when each phase closes.

---

## 📚 Documentation Index

### Essential References

| Document | Purpose | Last Updated |
|----------|---------|--------------|
| **[INDEX.md](INDEX.md)** | **This file** - Master navigation and quick links | 2026-03-28 |
| **[FIX_PLAN.md](FIX_PLAN.md)** | **Root cause analysis & fix plan for BUG-001 + BUG-002** | 2026-03-28 |
| **[DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)** | **Docker, credentials, testing, ports** | 2026-03-28 |

### Primary Trackers (Active Work)

| Document | Purpose | Last Updated |
|----------|---------|--------------|
| **[FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md)** | NodeSelectionModal status, triggers, actions, bugs | 2026-03-28 |
| **[FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md)** | Overall Flow UI status, backend integration, canvas | 2026-03-28 |

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

## 🔴 Critical Issues (detail)

Summary and ordered work: see **What we know** and **Fix plan** above. Deep dive:

- **BUG-001**: [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) → Issue #1  
- **BUG-002**: [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) → Critical Bugs  
- **BUG-003**: DocType combobox — same doc + **Implementation References** below

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

**P0 blockers** for Flow UI: **Fix plan** phases 1–2 (Actions tab #130, Flows page #185). The bug counts in the row above mix resolved and open items from the trackers.

---

## 🚀 Quick Actions

### For Bug Fixes
1. Read **What we know** and **Fix plan** at the top of this file
2. Check [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) and [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) for test notes and history

### For New Features
1. Check **Implementation References** above for similar working code
2. Check **Key Files** for where to make changes

### For Testing
1. Check `screenshots/` folder for visual evidence
2. Run `test_backend_core.py` for API tests
3. Use browser console to check for React errors
4. UI automation: Docker Browserless / CDP vs host Chrome — see [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) → *Browser automation*

---

## 📝 Update Log

| Date | Change | Commit |
|------|--------|--------|
| 2026-03-28 | Created FIX_PLAN.md with root cause analysis | - |
| 2026-03-28 | Created INDEX.md | - |
| 2026-03-28 | Added What we know + Fix plan, aligned BUG-002 partial | - |
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
