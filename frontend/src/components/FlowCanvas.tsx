import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  Panel
} from 'reactflow';
import 'reactflow/dist/style.css';
import { PanelLeftOpen, PanelRightOpen, Maximize2, Plus } from 'lucide-react';
import { Button } from './ui/button';
import { TriggerNode } from './nodes/TriggerNode';
import { ActionNode } from './nodes/ActionNode';
import { EndNode } from './nodes/EndNode';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { useFlowContext } from '../contexts/FlowContext';
import { FlowNodeData, TriggerConfig, ActionConfig } from '../types/flow.types';

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
  const { activeFlow, updateNodesAndEdges, updateNode, setSelectedNode, setSelectedEdge } = useFlowContext();
  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'trigger' | 'action'>('trigger');
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [sourceNodeForAction, setSourceNodeForAction] = useState<string | null>(null);

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
      setNodes((nds) => {
        const updatedNodes = applyNodeChanges(changes, nds);
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
      setEdges((eds) => {
        const updatedEdges = applyEdgeChanges(changes, eds);
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
        const newNodeId = `node-trigger-${Date.now()}`;
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

          const newNodeId = `node-${Date.now()}`;
          const iconMap: Record<string, string> = {
            'agent-run': 'Bot',
            'tool-call': 'Wrench',
            transform: 'Repeat',
            router: 'GitBranch',
            loop: 'RotateCw',
            'human-in-loop': 'UserCheck',
            code: 'Code',
            email: 'Mail',
            webhook: 'Webhook',
            file: 'FileText',
            date: 'Calendar'
          };

          const labelMap: Record<string, string> = {
            'agent-run': 'Run Agent',
            'tool-call': 'Call Tool',
            transform: 'Transform Data',
            router: 'Router',
            loop: 'Loop',
            'human-in-loop': 'Human in Loop',
            code: 'Execute Code',
            email: 'Send Email',
            webhook: 'Call Webhook',
            file: 'File Operations',
            date: 'Date Utility'
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

          return newEdges;
        });
        return currentNodes;
      });
    },
    [sourceNodeForAction, updateNodesAndEdges]
  );

  const nodeTypesWithAddButton = useMemo(
    () => ({
      trigger: (props: any) => <TriggerNode {...props} onAddNode={handleAddNode} />,
      action: (props: any) => <ActionNode {...props} onAddNode={handleAddNode} />,
      end: EndNode
    }),
    [handleAddNode]
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
    <div className="flex-1 relative w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypesWithAddButton}
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        className="bg-background w-full h-full"
      >
        <Background variant={'dots' as any} gap={16} size={2} color="oklch(var(--muted-foreground) / 0.35)" />
        <Controls className="!bottom-6" />
        <MiniMap
          nodeColor={(node) => {
            if (node.type === 'trigger') return 'oklch(var(--primary))';
            if (node.type === 'end') return '#10b981';
            return 'oklch(var(--muted))';
          }}
          className="!bg-background !border-border !bottom-6"
        />
        <Panel position="top-right" className="m-2">
          <div className="flex gap-2">
            {!nodes.some(n => n.data.nodeType === 'trigger') && (
              <Button
                variant="default"
                size="sm"
                className="rounded-full shadow-lg bg-primary text-primary-foreground hover:bg-primary/90"
                onClick={() => {
                  setModalMode('trigger');
                  setCurrentNodeId(null);
                  setIsModalOpen(true);
                }}
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Trigger
              </Button>
            )}
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10 rounded-full bg-background/60 backdrop-blur-sm"
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
              className="h-10 w-10 rounded-full bg-background/60 backdrop-blur-sm"
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
              className="h-10 w-10 rounded-full bg-background/60 backdrop-blur-sm"
              onClick={onToggleRightSidebar}
            >
              <PanelRightOpen className="w-4 h-4" />
            </Button>
          </Panel>
        )}
      </ReactFlow>

      <NodeSelectionModal
        open={isModalOpen}
        mode={modalMode}
        onClose={() => {
          setIsModalOpen(false);
          setCurrentNodeId(null);
          setSourceNodeForAction(null);
        }}
        onSaveTrigger={handleSaveTriggerConfig}
        onSaveAction={handleSelectAction}
      />
    </div>
  );
}
