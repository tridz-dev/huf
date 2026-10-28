import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Connection,
  Edge,
  NodeChange,
  EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  Node,
  Panel,
  BackgroundVariant
} from 'reactflow';
import 'reactflow/dist/style.css';
import { PanelLeftOpen, PanelRightOpen, Maximize2, Plus, Sparkles } from 'lucide-react';
import { Button } from './ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog';
import { actionHasConfiguredContent } from '../lib/flowNodeConfigured';
import { TriggerNode } from './nodes/TriggerNode';
import { ActionNode } from './nodes/ActionNode';
import { EndNode } from './nodes/EndNode';
import { AddStepGhostNode, AddStepGhostNodeData } from './nodes/AddStepGhostNode';
import { InsertableEdge, InsertableEdgeData } from './edges/InsertableEdge';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { FlowNodeRail, NODE_RAIL_ACTION_CATEGORY, NodeRailCategory } from './FlowNodeRail';
import { ConvertToProcedureDialog } from './ConvertToProcedureDialog';
import { DeleteStepDialog } from './flow/DeleteStepDialog';
import { connectionProblem } from '../lib/flowEdit';
import { useFlowContext } from '../contexts/FlowContext';
import { flowService } from '../services/flowService';
import { makeFlowEdge, edgeRoute } from '../services/flowSerializer';
import { branchHandlesFor } from '../lib/flowBranches';
import { branchColumnShift, subtreeIds } from '../lib/flowEdgeLabels';
import { toast } from 'sonner';
import { ensureToolSchemasLoaded } from '../lib/flowToolSchemas';
import { actionLabel, triggerLabel } from '../lib/flowLabels';
import { actionOptions } from '../data/actions';
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
    canUndo
  } = useFlowContext();
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
  }, [activeFlow?.id, activeFlow?.version, activeFlow?.nodes.length, activeFlow?.edges.length]); // Re-sync on ID/version change OR structural changes (add/delete)

  // Keyboard undo (Cmd/Ctrl+Z). Scoped to node deletion for now (see
  // FlowContext.undo). The "Undo" action on the delete toast is the primary,
  // discoverable path; this is the shortcut on top of it. Skipped while focus is in
  // a text field so it doesn't fight the input's own native undo.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isUndoCombo = (e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'z';
      if (!isUndoCombo) return;

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isEditable = tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable;
      if (isEditable || !canUndo) return;

      e.preventDefault();
      undo();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undo, canUndo]);

  // Persistent "was this saved as a Procedure?" indicator -- the save-time toast is
  // one-shot, so without this a user who saved with the checkbox on and then closed
  // the toast (or is looking at the flow later) has no way to tell whether a
  // Procedure exists, or find it, short of guessing its name on the Procedures page.
  const [convertedProcedure, setConvertedProcedure] = useState<string | null>(null);
  useEffect(() => {
    if (!activeFlow?.id) {
      setConvertedProcedure(null);
      return;
    }
    let cancelled = false;
    flowService.getConversionStatus(activeFlow.id).then((status) => {
      if (!cancelled) setConvertedProcedure(status.converted_procedure);
    }).catch(() => {
      if (!cancelled) setConvertedProcedure(null);
    });
    return () => {
      cancelled = true;
    };
    // Re-check after every save completes (saveState -> 'saved'), not just on
    // version bump -- the auto-convert checkbox's own conversion can complete
    // slightly after the flow doc save itself resolves.
  }, [activeFlow?.id, activeFlow?.version, saveState]);

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
    [scheduleContextUpdate, selectedNodeId, setSelectedNode]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      // Ghost edges (connecting a real leaf node to its synthesized "Add
      // step" placeholder) are render-only, same as ghost nodes above.
      // Filter their change events out before they can dirty the flow.
      const realChanges = changes.filter((change) => {
        const changeId = 'id' in change ? change.id : undefined;
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
    [scheduleContextUpdate]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const source = connection.source;
      const target = connection.target;
      const handle = connection.sourceHandle as FlowEdgeRoute | null;
      const route: FlowEdgeRoute = handle ?? 'next';
      const problem = connectionProblem({ nodes, edges }, { source, target, route });
      if (problem) {
        toast.error("Can't connect these steps", { description: problem, id: 'flow-connection-refused' });
        return;
      }
      const targetLabel = nodes.find((n) => n.id === target)?.data.label;
      // Single-target routes (next/true/false/approve/...) replace an existing edge on the same handle.
      const multi = route === 'option' || route === 'body';
      const kept = multi ? edges : edges.filter((e) => !(e.source === source && edgeRoute(e) === route));
      const index = kept.filter((e) => e.source === source && edgeRoute(e) === route).length;
      const newEdges = [...kept, makeFlowEdge(source, target, route, { label: targetLabel, index })];

      // Give each branch of a step its own column so a new path is never hidden behind another box.
      const targetNode = nodes.find((n) => n.id === target);
      const siblings = kept.filter((e) => e.source === source && e.target !== target).map((e) => nodes.find((n) => n.id === e.target)?.position.x);
      const shift = targetNode && siblings.length > 0
        ? branchColumnShift(targetNode.position.x, siblings.filter((x): x is number => typeof x === 'number'))
        : 0;
      let updatedNodes: Node<FlowNodeData>[] | undefined;
      if (shift !== 0) {
        const moving = subtreeIds(target, newEdges);
        updatedNodes = nodes.map((n) => (moving.has(n.id) ? { ...n, position: { ...n.position, x: n.position.x + shift } } : n));
        setNodes(updatedNodes);
      }
      setEdges(newEdges);
      if (!isSyncingFromProps.current) scheduleContextUpdate(updatedNodes, newEdges);
    },
    [scheduleContextUpdate, nodes, edges]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<FlowNodeData>) => {
      setSelectedNode(node.id);
      if (node.data.nodeType === 'trigger' && !node.data.triggerConfig?.type) {
        setCurrentNodeId(node.id);
        setModalMode('trigger');
        setIsModalOpen(true);
      }
    },
    [setSelectedNode]
  );

  const onEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      setSelectedEdge(edge.id);
    },
    [setSelectedEdge]
  );

  const onCanvasKeyDown = useCallback(
    (e: KeyboardEvent) => {
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
    [nodes, edges, selectedNodeId, selectedEdgeId, deleteNode]
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
      const sourceNode = nodes.find((n) => n.id === sourceId);
      if (!sourceNode) return;

      const newNodeId = `node_${Date.now()}`;
      const option = actionOptions.find((a) => a.id === actionId);
      const isEnd = actionId === 'end';
      // Fan branch targets out sideways (True/False, approve/reject, router paths) so they never stack on one spot.
      const sourceCfg = sourceNode.data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
      const sourceHandles = branchHandlesFor(sourceCfg?.type, sourceCfg);
      const routeIndex = sourceHandles.findIndex((h) => h.route === sourceRoute);
      const sideOffset = sourceHandles.length > 0 && routeIndex >= 0
        ? (routeIndex - (sourceHandles.length - 1) / 2) * 240
        : sourceCfg?.type === 'router'
          ? edges.filter((e) => e.source === sourceId && edgeRoute(e) === 'option').length * 240
          : 0;
      const newNode: Node<FlowNodeData> = {
        id: newNodeId,
        type: isEnd ? 'end' : 'action',
        position: { x: sourceNode.position.x + sideOffset, y: sourceNode.position.y + 150 },
        data: isEnd
          ? { label: actionLabel(actionId), nodeType: 'end', icon: option?.icon || 'CheckCircle2', configured: true, endConfig: {} }
          : {
            // The palette card name is the node title and the sidebar title.
            label: actionLabel(actionId),
            nodeType: 'action',
            icon: option?.icon || 'Play',
            configured: false,
            actionConfig: config
          }
      };

      // Edges that left the source on the same route move onto the new node (insertion mid-chain).
      const moving = edges.filter((e) => e.source === sourceId && edgeRoute(e) === sourceRoute);
      if (isEnd && moving.length > 0) {
        toast.error('End can only finish a path', { description: 'Add it at the open end of a path, not in front of another step.' });
        return;
      }
      const rest = edges.filter((e) => !moving.includes(e));
      const firstHandle = branchHandlesFor((config as { type?: string }).type)[0];
      const movedRoute: FlowEdgeRoute =
        (config as { type?: string }).type === 'router' ? 'option'
          : (config as { type?: string }).type === 'foreach' ? 'next'
            : firstHandle?.route ?? 'next';

      const newEdges = [
        ...rest,
        makeFlowEdge(sourceId, newNodeId, sourceRoute, { label: newNode.data.label, index: rest.filter((e) => e.source === sourceId && edgeRoute(e) === sourceRoute).length }),
        ...moving.map((e, i) => makeFlowEdge(newNodeId, e.target, movedRoute, { label: nodes.find((n) => n.id === e.target)?.data.label, index: i })),
      ];
      const updatedNodes = [...nodes, newNode];

      setNodes(updatedNodes);
      setEdges(newEdges);
      if (!isSyncingFromProps.current) updateNodesAndEdges(updatedNodes, newEdges);

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

  // Open ends of the graph: every (node, route) that still needs a successor. A plain step has one open
  // end (its 'next'); branching steps have one per missing branch.
  const openEnds = useMemo(() => {
    const ends: Array<{ nodeId: string; route: FlowEdgeRoute; handleId?: string; label?: string; position: { x: number; y: number }; offset: number }> = [];
    for (const n of nodes) {
      if (n.data.nodeType === 'end') continue;
      const out = edges.filter((e) => e.source === n.id);
      const cfg = n.data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
      if (cfg?.type === 'router') {
        if (!out.some((e) => edgeRoute(e) === 'option')) ends.push({ nodeId: n.id, route: 'option', handleId: 'option', label: 'Path', position: n.position, offset: 0 });
        continue;
      }
      const handles = branchHandlesFor(cfg?.type, cfg);
      if (handles.length === 0) {
        if (!out.some((e) => edgeRoute(e) === 'next')) ends.push({ nodeId: n.id, route: 'next', position: n.position, offset: 0 });
        continue;
      }
      handles.forEach((h, i) => {
        if (!out.some((e) => edgeRoute(e) === h.route)) {
          ends.push({ nodeId: n.id, route: h.route, handleId: h.handleId, label: h.label, position: n.position, offset: (i - (handles.length - 1) / 2) * 240 });
        }
      });
    }
    return ends;
  }, [nodes, edges]);

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
    // A leaf whose step below is not connected to it would draw its "Add step" card on top of that step:
    // slide the card sideways until the spot is free.
    const taken: Array<{ x: number; y: number }> = nodes.map((n) => n.position);
    return openEnds.map((end) => {
      let x = end.position.x + end.offset;
      const y = end.position.y + 150;
      let guard = 0;
      while (taken.some((p) => Math.abs(p.x - x) < 250 && Math.abs(p.y - y) < 90) && guard++ < 8) x += 280;
      taken.push({ x, y });
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
  }, [openEnds, nodes, handleAddNode]);

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

  const renderedNodes = useMemo(
    () => [...nodes, ...(ghostNodes as unknown as Node<FlowNodeData>[])],
    [nodes, ghostNodes]
  );

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
      <FlowNodeRail
        activeCategory={railActiveCategory}
        disabledCategories={railDisabledCategories}
        onSelect={handleRailSelect}
      />
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
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        className="bg-background w-full h-full"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={2} color="color-mix(in srgb, var(--muted-foreground) 35%, transparent)" />
        {/* showInteractive (lock toggle button) defaults to true, so it's already shown */}
        <Controls className="!bottom-6 !rounded-lg !border !border-line !overflow-hidden !shadow-sm" />
        <MiniMap
          position="top-left"
          ariaLabel="Flow overview"
          pannable
          zoomable
          nodeColor={(node) => {
            if (node.type === 'trigger') return 'var(--primary)';
            if (node.type === 'end') return 'var(--good)';
            return 'var(--muted)';
          }}
          className="!bg-background !border-border"
          style={{ width: 120, height: 80, borderRadius: 8, border: '1px solid var(--border)', boxShadow: '0 1px 3px color-mix(in srgb, var(--foreground) 12%, transparent)' }}
        />
        <Panel position="top-right" className="m-2">
          <div className="flex gap-2">
            {!nodes.some(n => n.data.nodeType === 'trigger') && (
              <Button
                variant="default"
                size="sm"
                data-testid="flow-add-trigger"
                onClick={() => {
                  setModalMode('trigger');
                  setCurrentNodeId(null);
                  setIsModalOpen(true);
                }}
              >
                <Plus className="w-4 h-4 mr-2" />
                Add trigger
              </Button>
            )}
            {activeFlow && convertedProcedure && (
              <Link to={`/procedures/${convertedProcedure}`}>
                <Button variant="outline" size="sm">
                  <Sparkles className="w-4 h-4 mr-2" />
                  Saved as procedure
                </Button>
              </Link>
            )}
            {activeFlow && !convertedProcedure && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsConvertDialogOpen(true)}
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Convert to procedure
              </Button>
            )}
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10"
              aria-label="Hide or show the side panels"
              title="Hide or show the side panels"
              data-testid="flow-toggle-panels"
              onClick={() => {
                if (showLeftSidebar || showRightSidebar) {
                  onToggleLeftSidebar();
                  onToggleRightSidebar();
                } else {
                  onToggleLeftSidebar();
                  onToggleRightSidebar();
                }
              }}
            >
              <Maximize2 className="w-4 h-4" />
            </Button>
          </div>
        </Panel>
        {!showLeftSidebar && (
          <Panel position="bottom-left" className="mb-4">
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10"
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
              className="h-10 w-10"
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

      <AlertDialog open={edgeDeleteId !== null} onOpenChange={(open) => !open && setEdgeDeleteId(null)}>
        <AlertDialogContent data-testid="flow-edge-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this connection?</AlertDialogTitle>
            <AlertDialogDescription>
              {(() => {
                const edge = edges.find((ed) => ed.id === edgeDeleteId);
                const from = nodes.find((n) => n.id === edge?.source)?.data.label ?? 'the step';
                const to = nodes.find((n) => n.id === edge?.target)?.data.label ?? 'the next step';
                return `"${from}" will no longer lead to "${to}". The steps stay on the canvas; connect them again or delete the one left over. You can undo this right after.`;
              })()}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="flow-edge-delete-confirm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (edgeDeleteId) deleteEdge(edgeDeleteId);
                setEdgeDeleteId(null);
              }}
            >
              Remove connection
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
