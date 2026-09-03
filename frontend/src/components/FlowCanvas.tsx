import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
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
import { TriggerNode } from './nodes/TriggerNode';
import { ActionNode } from './nodes/ActionNode';
import { EndNode } from './nodes/EndNode';
import { AddStepGhostNode, AddStepGhostNodeData } from './nodes/AddStepGhostNode';
import { InsertableEdge, InsertableEdgeData } from './edges/InsertableEdge';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { FlowNodeRail, NODE_RAIL_ACTION_CATEGORY, NodeRailCategory } from './FlowNodeRail';
import { ConvertToProcedureDialog } from './ConvertToProcedureDialog';
import { useFlowContext } from '../contexts/FlowContext';
import { flowService } from '../services/flowService';
import { FlowNodeData, TriggerConfig, ActionConfig } from '../types/flow.types';
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
    selectedNodeId,
    setSelectedNode,
    setSelectedEdge,
    saveState
  } = useFlowContext();
  const [isConvertDialogOpen, setIsConvertDialogOpen] = useState(false);
  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'trigger' | 'action'>('trigger');
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [sourceNodeForAction, setSourceNodeForAction] = useState<string | null>(null);
  const [modalActionCategory, setModalActionCategory] = useState<ActionOption['category'] | null>(null);

  // Track if we're currently syncing from props to prevent feedback loops
  const isSyncingFromProps = useRef(false);
  // Track pending updates to batch them
  const pendingUpdateRef = useRef<{ nodes?: Node<FlowNodeData>[]; edges?: Edge[] } | null>(null);
  const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null);

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

      setNodes((nds) => {
        const updatedNodes = applyNodeChanges(realChanges, nds);
        // Schedule context update (debounced)
        if (!isSyncingFromProps.current) {
          scheduleContextUpdate(updatedNodes, undefined);
        }
        return updatedNodes;
      });
    },
    [scheduleContextUpdate]
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

      setEdges((eds) => {
        const updatedEdges = applyEdgeChanges(realChanges, eds);
        // Schedule context update (debounced)
        if (!isSyncingFromProps.current) {
          scheduleContextUpdate(undefined, updatedEdges);
        }
        return updatedEdges;
      });
    },
    [scheduleContextUpdate]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => {
        const newEdges = addEdge(connection, eds);
        // Schedule context update (debounced)
        if (!isSyncingFromProps.current) {
          scheduleContextUpdate(undefined, newEdges);
        }
        return newEdges;
      });
    },
    [scheduleContextUpdate]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<FlowNodeData>) => {
      setSelectedNode(node.id);
      if (node.data.nodeType === 'trigger') {
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

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [setSelectedNode, setSelectedEdge]);

  const handleAddNode = useCallback((sourceNodeId: string) => {
    setSourceNodeForAction(sourceNodeId);
    setModalActionCategory(null);
    setModalMode('action');
    setIsModalOpen(true);
  }, []);

  const handleSaveTriggerConfig = useCallback(
    (config: TriggerConfig) => {
      const iconMap: Record<string, string> = {
        webhook: 'Webhook',
        schedule: 'Clock',
        'doc-event': 'Database',
        'app-trigger': 'Mail'
      };

      const labelMap: Record<string, string> = {
        webhook: 'Webhook',
        schedule: 'Schedule',
        'doc-event': 'Doc Event',
        'app-trigger': 'App Trigger'
      };

      if (currentNodeId) {
        const node = nodes.find((n) => n.id === currentNodeId);
        if (node) {
          updateNode(currentNodeId, {
            data: {
              ...node.data,
              label: labelMap[config.type || 'webhook'] || 'Trigger',
              icon: iconMap[config.type || 'webhook'],
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
    (actionType: string, config: ActionConfig) => {
      if (!sourceNodeForAction) return;

      setNodes((currentNodes) => {
        setEdges((currentEdges) => {
          const sourceNode = currentNodes.find((n) => n.id === sourceNodeForAction);
          if (!sourceNode) return currentEdges;

          const newNodeId = `node_${Date.now()}`;
          const iconMap: Record<string, string> = {
            'agent-run': 'Bot',
            'tool-call': 'Wrench',
            transform: 'Repeat',
            router: 'GitBranch',
            loop: 'RotateCw',
            'human.approval': 'UserCheck',
            code: 'Code',
            email: 'Mail',
            webhook: 'Webhook',
            file: 'FileText',
            date: 'Calendar'
          };

          const labelMap: Record<string, string> = {
            'agent-run': 'Run agent',
            'tool-call': 'Call tool',
            transform: 'Transform data',
            router: 'Router',
            loop: 'Loop',
            'human.approval': 'Human in loop',
            code: 'Execute code',
            email: 'Send email',
            file: 'File operations',
            // Previously missing, so these nodes fell through to the generic
            // 'Action' fallback below and the canvas showed no indication of
            // what the step actually did — a Condition node simply read
            // "Action". 'webhook' and 'date' are gone: those cards were
            // removed (HTTP Request supersedes webhook; no date tool exists).
            condition: 'Condition',
            'http-request': 'HTTP Request',
            slack: 'Slack',
            sheets: 'Google Sheets'
          };

          const newNode: Node<FlowNodeData> = {
            id: newNodeId,
            type: 'action',
            position: {
              x: sourceNode.position.x,
              y: sourceNode.position.y + 150
            },
            data: {
              label: labelMap[actionType] || 'Action',
              nodeType: 'action',
              icon: iconMap[actionType] || 'Play',
              configured: true,
              actionConfig: config
            }
          };

          const targetEdges = currentEdges.filter((e) => e.source === sourceNodeForAction);
          const newEdges = currentEdges.filter((e) => e.source !== sourceNodeForAction);

          newEdges.push({
            id: `edge-${Date.now()}`,
            source: sourceNodeForAction,
            target: newNodeId,
            type: 'default'
          });

          targetEdges.forEach((edge) => {
            newEdges.push({
              ...edge,
              id: `edge-${Date.now()}-${Math.random()}`,
              source: newNodeId
            });
          });

          const updatedNodes = [...currentNodes, newNode];

          // Direct update to context (not debounced) for explicit user actions
          if (!isSyncingFromProps.current) {
            updateNodesAndEdges(updatedNodes, newEdges);
          }

          setIsModalOpen(false);
          setSourceNodeForAction(null);
          setModalActionCategory(null);

          return newEdges;
        });
        return currentNodes;
      });
    },
    [sourceNodeForAction, updateNodesAndEdges]
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

  // Every node with no outgoing edge — the open ends of the graph, and the
  // only places a new step can be appended without rewiring by hand.
  const leafNodes = useMemo(() => {
    if (nodes.length === 0) return [];
    const sourceIds = new Set(edges.map((e) => e.source));
    return nodes.filter((n) => n.data.nodeType !== 'end' && !sourceIds.has(n.id));
  }, [nodes, edges]);

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
      case 'loop':
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
      setModalActionCategory(NODE_RAIL_ACTION_CATEGORY[category]);
      setModalMode('action');
      setIsModalOpen(true);
    },
    [nodes, insertionSourceId]
  );

  // Persistent "Add step" ghost card trailing the end of each open branch
  // (i.e. every node with no outgoing edge). Purely a render-time affordance —
  // it is never written back to the flow's nodes/edges via updateNodesAndEdges.
  const ghostNodes = useMemo<Node<AddStepGhostNodeData>[]>(() => {
    return leafNodes.map((leaf) => ({
      id: `ghost-${leaf.id}`,
      type: 'addStep',
      position: { x: leaf.position.x, y: leaf.position.y + 150 },
      draggable: false,
      selectable: false,
      connectable: false,
      data: { sourceNodeId: leaf.id, onAddNode: handleAddNode }
    }));
  }, [leafNodes, handleAddNode]);

  const ghostEdges = useMemo<Edge[]>(
    () =>
      ghostNodes.map((ghost) => ({
        id: `edge-${ghost.id}`,
        source: ghost.data.sourceNodeId,
        target: ghost.id,
        type: 'default',
        selectable: false,
        focusable: false
      })),
    [ghostNodes]
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
        data: { sourceNodeId: edge.source, onInsertNode: handleAddNode }
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
    <div className="flex-1 flex w-full h-full overflow-hidden">
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
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        className="bg-background w-full h-full"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={2} color="color-mix(in srgb, var(--muted-foreground) 35%, transparent)" />
        {/* showInteractive (lock toggle button) defaults to true, so it's already shown */}
        <Controls className="!bottom-6 !rounded-lg !border !border-line !overflow-hidden !shadow-sm" />
        <MiniMap
          nodeColor={(node) => {
            if (node.type === 'trigger') return 'var(--primary)';
            if (node.type === 'end') return 'var(--good)';
            return 'var(--muted)';
          }}
          className="!bg-background !border-border !bottom-6"
          style={{ width: 120, height: 80, borderRadius: 8, border: '1px solid var(--border)', boxShadow: '0 1px 3px color-mix(in srgb, var(--foreground) 12%, transparent)' }}
        />
        <Panel position="top-right" className="m-2">
          <div className="flex gap-2">
            {!nodes.some(n => n.data.nodeType === 'trigger') && (
              <Button
                variant="default"
                size="sm"
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
