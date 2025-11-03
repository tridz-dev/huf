import { useCallback, useEffect, useMemo, useState } from 'react';
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
import { PanelLeftOpen, PanelRightOpen, Maximize2 } from 'lucide-react';
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
  const { activeFlow, updateNodesAndEdges, updateNode, setSelectedNode } = useFlowContext();
  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'trigger' | 'action'>('trigger');
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [sourceNodeForAction, setSourceNodeForAction] = useState<string | null>(null);

  useEffect(() => {
    if (activeFlow) {
      setNodes(activeFlow.nodes);
      setEdges(activeFlow.edges);
    }
  }, [activeFlow]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((nds) => {
        const updatedNodes = applyNodeChanges(changes, nds);
        if (activeFlow) {
          updateNodesAndEdges(updatedNodes, edges);
        }
        return updatedNodes;
      });
    },
    [edges, activeFlow, updateNodesAndEdges]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((eds) => {
        const updatedEdges = applyEdgeChanges(changes, eds);
        if (activeFlow) {
          updateNodesAndEdges(nodes, updatedEdges);
        }
        return updatedEdges;
      });
    },
    [nodes, activeFlow, updateNodesAndEdges]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => {
        const newEdges = addEdge(connection, eds);
        if (activeFlow) {
          updateNodesAndEdges(nodes, newEdges);
        }
        return newEdges;
      });
    },
    [nodes, activeFlow, updateNodesAndEdges]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<FlowNodeData>) => {
      setSelectedNode(node.id);
      if (node.data.nodeType === 'trigger' && !node.data.configured) {
        setCurrentNodeId(node.id);
        setModalMode('trigger');
        setIsModalOpen(true);
      }
    },
    [setSelectedNode]
  );

  const handleAddNode = useCallback((sourceNodeId: string) => {
    setSourceNodeForAction(sourceNodeId);
    setModalMode('action');
    setIsModalOpen(true);
  }, []);

  const handleSaveTriggerConfig = useCallback(
    (config: TriggerConfig) => {
      if (currentNodeId) {
        const node = nodes.find((n) => n.id === currentNodeId);
        if (node) {
          const iconMap: Record<string, string> = {
            webhook: 'Webhook',
            schedule: 'Clock',
            'doc-event': 'Database',
            'app-trigger': 'Mail'
          };

          updateNode(currentNodeId, {
            data: {
              ...node.data,
              label: config.type === 'webhook' ? 'Webhook' :
                     config.type === 'schedule' ? 'Schedule' :
                     config.type === 'doc-event' ? 'Doc Event' :
                     'App Trigger',
              icon: iconMap[config.type || 'webhook'],
              configured: true,
              triggerConfig: config
            }
          });
        }
      }
      setIsModalOpen(false);
      setCurrentNodeId(null);
    },
    [currentNodeId, nodes, updateNode]
  );

  const handleSelectAction = useCallback(
    (actionType: string, config: ActionConfig) => {
      if (!sourceNodeForAction || !activeFlow) return;

      const sourceNode = nodes.find((n) => n.id === sourceNodeForAction);
      if (!sourceNode) return;

      const newNodeId = `node-${Date.now()}`;
      const iconMap: Record<string, string> = {
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

      const targetEdges = edges.filter((e) => e.source === sourceNodeForAction);
      const newEdges = edges.filter((e) => e.source !== sourceNodeForAction);

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

      const updatedNodes = [...nodes, newNode];
      updateNodesAndEdges(updatedNodes, newEdges);
      setIsModalOpen(false);
      setSourceNodeForAction(null);
    },
    [sourceNodeForAction, activeFlow, nodes, edges, updateNodesAndEdges]
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
