# Fix Flow UI Critical Bugs (BUG-001 + BUG-002)

> **Date**: 2026-03-28  
> **Branch**: `feature/flow-backend-integration`  
> **Status**: Ready to implement

Two P0 bugs block the Flow Builder UI. Both are frontend-only — backend APIs are working.

---

## Root Cause Analysis

### BUG-001: Actions Tab Crash (React #130)

**Three interrelated data/type issues:**

1. `ActionOption.category` in [`modal.types.ts`](frontend/src/types/modal.types.ts) only allows `'transform' | 'control' | 'utility' | 'integration'` — **missing `'agent'` and `'tool'`**.
2. [`actions.ts`](frontend/src/data/actions.ts) sets both "Run Agent" and "Call Tool" to `category: 'transform'` (the only valid option) instead of `'agent'` and `'tool'`.
3. [`NodeSelectionModal.tsx`](frontend/src/components/modals/NodeSelectionModal.tsx) filters for `category === 'agent'` and `category === 'tool'` — these buckets are **always empty**, so "AI & Agents" and "Tools" sections never render.

> [!IMPORTANT]
> Previous fix attempts all focused on icons (imports, iconMap, null checks). The real issue is the **data model mismatch** between types, data, and filter logic.

### BUG-002: Infinite Loop (React #185)

**Circular state update between FlowCanvas and FlowContext:**

```
activeFlow changes
  → FlowCanvas useEffect sets local nodes/edges
  → React Flow fires onNodesChange (dimension recalc)
  → onNodesChange calls updateNodesAndEdges
  → flowService.updateNodesAndEdges updates cache + notifies listeners
  → FlowContext subscriber calls setActiveFlowState(cached)
  → activeFlow changes → LOOP
```

### Bonus: saveFlow Signature Mismatch

`FlowContext.saveFlow` passes `activeFlowId` (string) to `flowService.saveFlow()`, but the service method expects a `Flow` object. This would crash on any save attempt.

---

## Proposed Changes

### 1. Fix ActionOption type

#### [MODIFY] [modal.types.ts](frontend/src/types/modal.types.ts)

```diff
-  category: 'transform' | 'control' | 'utility' | 'integration';
+  category: 'agent' | 'tool' | 'transform' | 'control' | 'utility' | 'integration';
```

---

### 2. Fix action categories

#### [MODIFY] [actions.ts](frontend/src/data/actions.ts)

```diff
   {
     id: 'agent-run',
     name: 'Run Agent',
     icon: 'Bot',
-    category: 'transform'
+    category: 'agent'
   },
   {
     id: 'tool-call',
     name: 'Call Tool',
     icon: 'Wrench',
-    category: 'transform'
+    category: 'tool'
   },
```

Add missing actions for remaining categories (transform, utility, integration).

---

### 3. Break the infinite loop

#### [MODIFY] [FlowCanvas.tsx](frontend/src/components/FlowCanvas.tsx)

Add a `isSyncingRef` guard to prevent writing back to context when local state change originated from context sync (not user interaction).

```diff
+ const isSyncingRef = useRef(false);

  useEffect(() => {
    if (activeFlow) {
+     isSyncingRef.current = true;
      setNodes(activeFlow.nodes);
      setEdges(activeFlow.edges);
+     requestAnimationFrame(() => { isSyncingRef.current = false; });
    }
  }, [activeFlow]);

  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => {
      const updatedNodes = applyNodeChanges(changes, nds);
-     if (activeFlow) {
+     if (activeFlow && !isSyncingRef.current) {
        updateNodesAndEdges(updatedNodes, edges);
      }
      return updatedNodes;
    });
  }, ...);
```

Same guard applied to `onEdgesChange` and `onConnect`.

---

### 4. Fix saveFlow signature

#### [MODIFY] [FlowContext.tsx](frontend/src/contexts/FlowContext.tsx)

```diff
  const saveFlow = useCallback(async () => {
-   if (!activeFlowId || !hasUnsavedChanges) return;
+   if (!activeFlowId || !activeFlow || !hasUnsavedChanges) return;
    setSaveState('saving');
    try {
-     await flowService.saveFlow(activeFlowId);
+     await flowService.saveFlow(activeFlow);
```

---

## Verification Plan

### Browser Testing (localhost:8001)
1. Login as `Administrator`/`admin`
2. Navigate to Flows page
3. **BUG-002**: Confirm no React #185 errors, page loads cleanly
4. Open/create a flow, click "+" on a node
5. **BUG-001**: Click "Actions" tab — verify all categories render without crash
6. Click actions, verify they dispatch correctly

### TypeScript Check
```bash
cd frontend && yarn typecheck
```

---

## Files Affected

| File | Change |
|------|--------|
| [`modal.types.ts`](frontend/src/types/modal.types.ts) | Add `'agent'` + `'tool'` to category union |
| [`actions.ts`](frontend/src/data/actions.ts) | Fix categories, add missing actions |
| [`FlowCanvas.tsx`](frontend/src/components/FlowCanvas.tsx) | Add syncing guard ref |
| [`FlowContext.tsx`](frontend/src/contexts/FlowContext.tsx) | Fix saveFlow signature |

---

## Related Docs

- [FLOW_NODE_MODAL_TRACKER.md](FLOW_NODE_MODAL_TRACKER.md) — Modal bug details
- [FLOW_UI_FEATURE_TRACKER.md](FLOW_UI_FEATURE_TRACKER.md) — Overall UI status
- [INDEX.md](INDEX.md) — Master index

---

*Update this document after each fix is verified.*
