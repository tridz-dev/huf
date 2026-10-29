import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Connection,
  Edge,
  NodeChange,
  EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  Node,
  Panel,
  BackgroundVariant,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react';
import { Button } from './ui/button';
import { actionHasConfiguredContent } from '../lib/flow/flowNodeConfigured';
import { TriggerNode } from './nodes/TriggerNode';
import { ActionNode } from './nodes/ActionNode';
import { EndNode } from './nodes/EndNode';
import { AddStepGhostNode, AddStepGhostNodeData } from './nodes/AddStepGhostNode';
import { InsertableEdge, InsertableEdgeData } from './edges/InsertableEdge';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { FlowNodeRail, NODE_RAIL_ACTION_CATEGORY, NodeRailCategory } from './FlowNodeRail';
import { ConvertToProcedureDialog } from './ConvertToProcedureDialog';
import { DeleteStepDialog } from './flow/DeleteStepDialog';
import { FIT_VIEW_OPTIONS, FitViewAfterRemovalOrLayout, FlowControls, FlowMiniMap, keepCanvasUnscrolled, withSelection } from './flow/canvas/canvasView';
import { FlowCanvasToolbar } from './flow/canvas/FlowCanvasToolbar';
import { EdgeDeleteDialog } from './flow/canvas/EdgeDeleteDialog';
import { useConvertedProcedure, useUndoShortcut } from './flow/canvas/useCanvasEffects';
import { connectionProblem } from '../lib/flow/flowEdit';
import { useFlowContext } from '../contexts/FlowContext';
import { edgeRoute } from '../services/flowSerializer';
import { addActionStep, computeOpenEnds, connectSteps, connectionRoute, ghostPositions } from '../lib/flow-graph/flowCanvasGraph';
import { toast } from '@/lib/toast';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { FirstRunGuide } from './flow/FirstRunGuide';
import { ensureToolSchemasLoaded } from '../lib/flow/flowToolSchemas';
import { triggerLabel } from '../lib/flow/flowLabels';
import { FlowNodeData, TriggerConfig, ActionConfig, FlowEdgeRoute } from '../types/flow.types';
import type { ActionOption } from '../types/modal.types';

interface FlowCanvasProps {
  showLeftSidebar: boolean;
  showRightSidebar: boolean;
  onToggleLeftSidebar: () => void;
  onToggleRightSidebar: () => void;
}

export function FlowCanvas({
  showLeftSidebar,
  showRightSidebar,
  onToggleLeftSidebar,
  onToggleRightSidebar
}: FlowCanvasProps) {
  const {
    activeFlow,
    updateNodesAndEdges,
    updateNode,
    deleteNode,
    selectedNodeId,
    selectedEdgeId,
    setSelectedNode,
    setSelectedEdge,
    deleteEdge,
    saveState,
    undo,
    canUndo,
    tidyLayout,
    layoutRevision,
  } = useFlowContext();
  const { canManage, readOnlyReason } = useFlowPermissions();
  const [isConvertDialogOpen, setIsConvertDialogOpen] = useState(false);
  // Delete / Backspace on a selected step asks first (the click-to-delete buttons already do).
  const [keyboardDeleteId, setKeyboardDeleteId] = useState<string | null>(null);
  // Same for a selected connection: the button on the line and the Delete key both ask first.
  const [edgeDeleteId, setEdgeDeleteId] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'trigger' | 'action'>('trigger');
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [sourceNodeForAction, setSourceNodeForAction] = useState<string | null>(null);
  const [sourceRouteForAction, setSourceRouteForAction] = useState<FlowEdgeRoute>('next');
  const [modalActionCategory, setModalActionCategory] = useState<ActionOption['category'] | null>(null);

  // Track if we're currently syncing from props to prevent feedback loops
  const isSyncingFromProps = useRef(false);
  // Track pending updates to batch them
  const pendingUpdateRef = useRef<{ nodes?: Node<FlowNodeData>[]; edges?: Edge[] } | null>(null);
  const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Learn each tool's required inputs so validation can block incomplete tool steps.
  useEffect(() => {
    void ensureToolSchemasLoaded();
  }, []);

  // Sync from activeFlow to local state when flow changes (not on every node/edge update)
  useEffect(() => {
    if (activeFlow) {
      // Cancel any pending debounced updates to avoid re-applying stale nodes/edges
      // after a context-driven graph change (e.g., delete button).
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
        updateTimeoutRef.current = null;
      }
      pendingUpdateRef.current = null;

      isSyncingFromProps.current = true;
      setNodes(activeFlow.nodes);
      setEdges(activeFlow.edges);
      // Clear the guard after React has processed the batched state updates
      requestAnimationFrame(() => {
        isSyncingFromProps.current = false;
      });
    }
  }, [activeFlow?.id, activeFlow?.version, activeFlow?.nodes.length, activeFlow?.edges.length, layoutRevision]); // Re-sync on ID/version change OR structural changes (add/delete)

  useUndoShortcut(undo, canUndo);

  const convertedProcedure = useConvertedProcedure(activeFlow?.id, activeFlow?.version, saveState);

  // Debounced update to context to batch rapid changes
  const scheduleContextUpdate = useCallback((newNodes?: Node<FlowNodeData>[], newEdges?: Edge[]) => {
    if (isSyncingFromProps.current) return;

    // Accumulate pending updates
    pendingUpdateRef.current = {
      nodes: newNodes ?? pendingUpdateRef.current?.nodes,
      edges: newEdges ?? pendingUpdateRef.current?.edges,
    };

    // Clear existing timeout
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
    }

    // Schedule update
    updateTimeoutRef.current = setTimeout(() => {
      if (pendingUpdateRef.current && activeFlow) {
        const { nodes: pendingNodes, edges: pendingEdges } = pendingUpdateRef.current;
        updateNodesAndEdges(
          pendingNodes ?? nodes,
          pendingEdges ?? edges
        );
        pendingUpdateRef.current = null;
      }
    }, 50); // 50ms debounce
  }, [activeFlow, nodes, edges, updateNodesAndEdges]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, []);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // Ghost "Add step" placeholders are synthesized purely for rendering
      // (see `ghostNodes` below) and are never part of the real `nodes`
      // state that gets written back to the flow. ReactFlow still emits
      // change events for them (e.g. dimension measurements), which would
      // otherwise flow into applyNodeChanges/scheduleContextUpdate and mark
      // the flow "unsaved" even though nothing real changed. Drop them here.
      const realChanges = changes.filter((change) => {
        const changeId = 'id' in change ? change.id : undefined;
        if (!canManage && change.type !== 'select' && change.type !== 'dimensions') return false; // view-only: nothing moves or goes away
        return !changeId || !changeId.startsWith('ghost-');
      });
      if (realChanges.length === 0) return;

      // Keyboard selection (Tab to a step, Enter) opens that step's settings like a click does.
      const picked = realChanges.find((c) => c.type === 'select' && c.selected);
      if (picked && 'id' in picked && picked.id !== selectedNodeId) setSelectedNode(picked.id);

      // Measurements and selection are view state, not edits. React Flow can emit them
      // after the post-save re-sync guard has cleared, which flipped a just-saved flow
      // back to "Unsaved", so only real edits (move, add, remove, replace) schedule a write.
      // A plain click ends with a position change that carries no new position: that is not a move either.
      const isEdit = realChanges.some(
        (change) =>
          change.type !== 'dimensions' &&
          change.type !== 'select' &&
          !(change.type === 'position' && change.position === undefined)
      );

      setNodes((nds) => {
        const updatedNodes = applyNodeChanges(realChanges, nds);
        // Schedule context update (debounced)
        if (isEdit && !isSyncingFromProps.current) {
          scheduleContextUpdate(updatedNodes, undefined);
        }
        return updatedNodes;
      });
    },
    [canManage, scheduleContextUpdate, selectedNodeId, setSelectedNode]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      // Ghost edges (connecting a real leaf node to its synthesized "Add
      // step" placeholder) are render-only, same as ghost nodes above.
      // Filter their change events out before they can dirty the flow.
      const realChanges = changes.filter((change) => {
        const changeId = 'id' in change ? change.id : undefined;
        if (!canManage && change.type !== 'select') return false;
        return !changeId || !changeId.startsWith('edge-ghost-');
      });
      if (realChanges.length === 0) return;
      // Selecting or deselecting an edge is view state, not an edit.
      const isEdgeEdit = realChanges.some((change) => change.type !== 'select');

      setEdges((eds) => {
        const updatedEdges = applyEdgeChanges(realChanges, eds);
        // Schedule context update (debounced)
        if (isEdgeEdit && !isSyncingFromProps.current) {
          scheduleContextUpdate(undefined, updatedEdges);
        }
        return updatedEdges;
      });
    },
    [canManage, scheduleContextUpdate]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!canManage || !connection.source || !connection.target) return;
      const source = connection.source;
      const target = connection.target;
      const route = connectionRoute(connection);
      const problem = connectionProblem({ nodes, edges }, { source, target, route });
      if (problem) {
        toast.error("Can't connect these steps", { description: problem, id: 'flow-connection-refused' });
        return;
      }
      const { newEdges, updatedNodes } = connectSteps(nodes, edges, source, target, route);
      if (updatedNodes) setNodes(updatedNodes);
      setEdges(newEdges);
      if (!isSyncingFromProps.current) scheduleContextUpdate(updatedNodes, newEdges);
    },
    [canManage, scheduleContextUpdate, nodes, edges]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<FlowNodeData>) => {
      setSelectedNode(node.id);
      if (canManage && node.data.nodeType === 'trigger' && !node.data.triggerConfig?.type) {
        setCurrentNodeId(node.id);
        setModalMode('trigger');
        setIsModalOpen(true);
      }
    },
    [canManage, setSelectedNode]
  );

  const onEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      setSelectedEdge(edge.id);
    },
    [setSelectedEdge]
  );

  const onCanvasKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!canManage) return;
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable || target?.closest('[role="dialog"], [role="alertdialog"], [role="combobox"], [role="listbox"], [role="menu"]')) return;
      // Only when the user is on the canvas (or nowhere in particular), never in another part of the page.
      if (target && target !== document.body && !target.closest('[data-testid="flow-canvas"]')) return;
      const node = nodes.find((n) => n.selected && !n.id.startsWith('ghost-')) ?? nodes.find((n) => n.id === selectedNodeId);
      if (!node) {
        // No step selected: Delete removes the selected connection (after asking).
        const edge = edges.find((ed) => ed.selected && !ed.id.startsWith('edge-ghost-')) ?? edges.find((ed) => ed.id === selectedEdgeId);
        if (edge) {
          e.preventDefault();
          setEdgeDeleteId(edge.id);
        }
        return;
      }
      if (node.data.status === 'running' || node.data.status === 'waiting') return;
      e.preventDefault();
      if (node.data.nodeType === 'action' && !actionHasConfiguredContent(node.data)) {
        deleteNode(node.id);
        return;
      }
      setKeyboardDeleteId(node.id);
    },
    [canManage, nodes, edges, selectedNodeId, selectedEdgeId, deleteNode]
  );

  useEffect(() => {
    window.addEventListener('keydown', onCanvasKeyDown);
    return () => window.removeEventListener('keydown', onCanvasKeyDown);
  }, [onCanvasKeyDown]);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [setSelectedNode, setSelectedEdge]);

  const handleAddNode = useCallback((sourceNodeId: string, route: FlowEdgeRoute = 'next') => {
    setSourceNodeForAction(sourceNodeId);
    setSourceRouteForAction(route);
    setModalActionCategory(null);
    setModalMode('action');
    setIsModalOpen(true);
  }, []);

  const handleSaveTriggerConfig = useCallback(
    (config: TriggerConfig) => {
      const iconMap: Record<string, string> = {
        webhook: 'Webhook',
        schedule: 'Clock',
        'doc-event': 'Database'
      };
      const labelMap: Record<string, string> = {
        webhook: triggerLabel('webhook'),
        schedule: triggerLabel('schedule'),
        'doc-event': triggerLabel('doc-event')
      };

      if (currentNodeId) {
        const node = nodes.find((n) => n.id === currentNodeId);
        if (node) {
          updateNode(currentNodeId, {
            data: {
              ...node.data,
              label: labelMap[config.type || 'webhook'] || 'Trigger',
              icon: iconMap[config.type || 'webhook'],
              // Drop the "Select a trigger" hint of the placeholder once a trigger is chosen.
              description: undefined,
              configured: true,
              triggerConfig: config
            }
          });
        }
      } else {
        // Create a new trigger node
        const newNodeId = `node_trigger_${Date.now()}`;
        const newNode: Node<FlowNodeData> = {
          id: newNodeId,
          type: 'trigger',
          position: { x: 250, y: 100 },
          data: {
            label: labelMap[config.type || 'webhook'] || 'Trigger',
            nodeType: 'trigger',
            icon: iconMap[config.type || 'webhook'],
            configured: true,
            triggerConfig: config
          }
        };

        setNodes((nds) => {
          const updatedNodes = [...nds, newNode];
          updateNodesAndEdges(updatedNodes, edges);
          return updatedNodes;
        });
      }
      setIsModalOpen(false);
      setCurrentNodeId(null);
    },
    [currentNodeId, nodes, updateNode]
  );

  const handleSelectAction = useCallback(
    (actionId: string, config: ActionConfig) => {
      if (!sourceNodeForAction) return;
      const sourceId = sourceNodeForAction;
      const sourceRoute = sourceRouteForAction;
      const added = addActionStep(nodes, edges, sourceId, sourceRoute, actionId, config);
      if (!added) return;
      if (added === 'end-in-front') {
        toast.error('End can only finish a path', { description: 'Add it at the open end of a path, not in front of another step.' });
        return;
      }
      setNodes(added.nodes);
      setEdges(added.edges);
      if (!isSyncingFromProps.current) updateNodesAndEdges(added.nodes, added.edges);

      setIsModalOpen(false);
      setSourceNodeForAction(null);
      setModalActionCategory(null);
      setSourceRouteForAction('next');
    },
    [sourceNodeForAction, sourceRouteForAction, nodes, edges, updateNodesAndEdges]
  );

  const nodeTypesWithAddButton = useMemo(
    () => ({
      trigger: TriggerNode,
      action: ActionNode,
      end: EndNode,
      addStep: AddStepGhostNode
    }),
    []
  );

  const edgeTypesWithInsert = useMemo(() => ({ insertable: InsertableEdge }), []);

  const openEnds = useMemo(() => computeOpenEnds(nodes, edges), [nodes, edges]);

  const leafNodes = useMemo(() => {
    const ids = new Set(openEnds.map((o) => o.nodeId));
    return nodes.filter((n) => ids.has(n.id));
  }, [nodes, openEnds]);

  // Where a rail click inserts: after the selected node when there is one
  // (handleSelectAction rewires the downstream edge), otherwise at the last
  // open end of the graph — the same spot the trailing ghost card targets.
  const insertionSourceId = useMemo(() => {
    if (selectedNodeId) {
      const selected = nodes.find((n) => n.id === selectedNodeId);
      if (selected && selected.data.nodeType !== 'end') return selected.id;
    }
    return leafNodes.length > 0 ? leafNodes[leafNodes.length - 1].id : null;
  }, [selectedNodeId, nodes, leafNodes]);

  const railActiveCategory = useMemo<NodeRailCategory | null>(() => {
    const selected = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : undefined;
    if (!selected) return null;
    if (selected.data.nodeType === 'trigger') return 'trigger';
    switch (selected.data.actionConfig?.type) {
      case 'agent-run':
        return 'agent';
      case 'tool-call':
        return 'tool';
      case 'condition':
      case 'router':
      case 'foreach':
        return 'condition';
      default:
        return null;
    }
  }, [selectedNodeId, nodes]);

  const railDisabledCategories = useMemo<NodeRailCategory[]>(
    () => (insertionSourceId ? [] : ['agent', 'condition', 'tool', 'data']),
    [insertionSourceId]
  );

  const handleRailSelect = useCallback(
    (category: NodeRailCategory) => {
      if (category === 'trigger') {
        const existingTrigger = nodes.find((n) => n.data.nodeType === 'trigger');
        setSourceNodeForAction(null);
        setModalActionCategory(null);
        setCurrentNodeId(existingTrigger?.id ?? null);
        setModalMode('trigger');
        setIsModalOpen(true);
        return;
      }
      if (!insertionSourceId) return;
      setSourceNodeForAction(insertionSourceId);
      setSourceRouteForAction(openEnds.find((o) => o.nodeId === insertionSourceId)?.route ?? 'next');
      setModalActionCategory(NODE_RAIL_ACTION_CATEGORY[category]);
      setModalMode('action');
      setIsModalOpen(true);
    },
    [nodes, insertionSourceId, openEnds]
  );

  // Persistent "Add step" ghost card trailing the end of each open branch
  // (i.e. every node with no outgoing edge). Purely a render-time affordance —
  // it is never written back to the flow's nodes/edges via updateNodesAndEdges.
  const ghostNodes = useMemo<Node<AddStepGhostNodeData>[]>(() => {
    if (!canManage) return []; // view-only: no "Add step" cards
    const spots = ghostPositions(nodes, openEnds);
    return openEnds.map((end, i) => {
      const { x, y } = spots[i];
      return {
        id: `ghost-${end.nodeId}-${end.route}`,
        type: 'addStep',
        position: { x, y },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false, // its own button is the control; the wrapper must not be a second, nested one
        data: { sourceNodeId: end.nodeId, route: end.route, branchLabel: end.label, onAddNode: handleAddNode }
      };
    });
  }, [canManage, openEnds, nodes, handleAddNode]);

  const ghostEdges = useMemo<Edge[]>(
    () =>
      ghostNodes.map((ghost) => ({
        id: `edge-${ghost.id}`,
        source: ghost.data.sourceNodeId,
        sourceHandle: openEnds.find((o) => `ghost-${o.nodeId}-${o.route}` === ghost.id)?.handleId,
        target: ghost.id,
        type: 'default',
        selectable: false,
        focusable: false
      })),
    [ghostNodes, openEnds]
  );

  // The highlighted step always follows the selection the side panel shows (see withSelection).
  const renderedNodes = useMemo(() => [...withSelection(nodes, selectedNodeId), ...(ghostNodes as unknown as Node<FlowNodeData>[])], [nodes, ghostNodes, selectedNodeId]);

  // Real edges get the hover "+" insert affordance (mid-chain insertion);
  // ghost edges (leading to the trailing "Add step" card) render as plain
  // edges since that leaf already has its own persistent affordance.
  const insertableEdges = useMemo<Edge<InsertableEdgeData>[]>(
    () =>
      edges.map((edge) => ({
        ...edge,
        type: 'insertable',
        data: { ...(edge.data ?? {}), sourceNodeId: edge.source, route: edgeRoute(edge), onInsertNode: handleAddNode, onRemove: (edgeId: string) => setEdgeDeleteId(edgeId) }
      })),
    [edges, handleAddNode]
  );
  const renderedEdges = useMemo(
    () => [...insertableEdges, ...ghostEdges],
    [insertableEdges, ghostEdges]
  );

  if (!activeFlow) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="text-muted-foreground mb-2">No flow selected</div>
          <div className="text-sm text-muted-foreground">
            Select a flow from the sidebar to get started
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex w-full h-full overflow-hidden" data-testid="flow-canvas">
      {canManage && (
      <FlowNodeRail
        activeCategory={railActiveCategory}
        disabledCategories={railDisabledCategories}
        onSelect={handleRailSelect}
      />
      )}
      <div className="relative flex-1 h-full min-w-0">
      <ReactFlow
        nodes={renderedNodes}
        edges={renderedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypesWithAddButton}
        edgeTypes={edgeTypesWithInsert}
        deleteKeyCode={null}
        nodesDraggable={canManage}
        nodesConnectable={canManage}
        elementsSelectable
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={FIT_VIEW_OPTIONS.minZoom}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        className="bg-background w-full h-full"
        onScroll={keepCanvasUnscrolled}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={2} color="color-mix(in srgb, var(--muted-foreground) 35%, transparent)" />
        {/* showInteractive (lock toggle button) defaults to true, so it's already shown */}
        <FlowControls className="!bottom-6 !rounded-lg !border !border-line !overflow-hidden !shadow-sm" />
        <FlowMiniMap />
        <FitViewAfterRemovalOrLayout flowId={activeFlow?.id} nodeCount={activeFlow?.nodes.length ?? 0} edgeCount={activeFlow?.edges.length ?? 0} layoutRevision={layoutRevision} />
        {canManage && nodes.length <= 1 && (
          <Panel position="top-center" className="mt-[68px]">
            <FirstRunGuide />
          </Panel>
        )}
        <Panel position="top-right" className="m-2">
          <FlowCanvasToolbar
            canManage={canManage}
            readOnlyReason={readOnlyReason}
            hasTrigger={nodes.some((n) => n.data.nodeType === 'trigger')}
            hasSteps={nodes.length > 1}
            convertedProcedure={convertedProcedure}
            onAddTrigger={() => {
              setModalMode('trigger');
              setCurrentNodeId(null);
              setIsModalOpen(true);
            }}
            onTidy={tidyLayout}
            onConvert={() => setIsConvertDialogOpen(true)}
            onTogglePanels={() => {
              onToggleLeftSidebar();
              onToggleRightSidebar();
            }}
          />
        </Panel>
        {!showLeftSidebar && (
          <Panel position="top-left" className="m-2">
            <Button
              variant="outline"
              size="icon"
              className="h-control-lg w-control-lg"
              aria-label="Show the flow list"
              title="Show the flow list"
              onClick={onToggleLeftSidebar}
            >
              <PanelLeftOpen className="w-4 h-4" />
            </Button>
          </Panel>
        )}
        {!showRightSidebar && (
          <Panel position="bottom-right" className="mb-4">
            <Button
              variant="outline"
              size="icon"
              className="h-control-lg w-control-lg"
              aria-label="Show step settings"
              title="Show step settings"
              data-testid="flow-open-settings"
              onClick={onToggleRightSidebar}
            >
              <PanelRightOpen className="w-4 h-4" />
            </Button>
          </Panel>
        )}
      </ReactFlow>
      </div>

      <NodeSelectionModal
        open={isModalOpen}
        mode={modalMode}
        actionCategory={modalActionCategory}
        onClose={() => {
          setIsModalOpen(false);
          setCurrentNodeId(null);
          setSourceNodeForAction(null);
          setModalActionCategory(null);
        }}
        onSaveTrigger={handleSaveTriggerConfig}
        onSaveAction={handleSelectAction}
      />

      <EdgeDeleteDialog
        edgeId={edgeDeleteId}
        nodes={nodes}
        edges={edges}
        onCancel={() => setEdgeDeleteId(null)}
        onConfirm={deleteEdge}
      />

      <DeleteStepDialog nodeId={keyboardDeleteId} onOpenChange={(open) => !open && setKeyboardDeleteId(null)} />

      {activeFlow && (
        <ConvertToProcedureDialog
          flowId={activeFlow.id}
          open={isConvertDialogOpen}
          onOpenChange={setIsConvertDialogOpen}
        />
      )}
    </div>
  );
}
