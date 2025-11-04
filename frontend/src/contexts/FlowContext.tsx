import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { Flow, FlowMetadata, FlowNode, FlowEdge } from '../types/flow.types';
import { flowService } from '../services/flowService';

interface FlowContextType {
  flows: FlowMetadata[];
  activeFlowId: string | null;
  activeFlow: Flow | null;
  selectedNodeId: string | null;
  setActiveFlow: (flowId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;
  createFlow: (name: string, category?: string) => Flow;
  updateFlowName: (flowId: string, name: string) => void;
  deleteFlow: (flowId: string) => void;
  updateNodes: (nodes: FlowNode[]) => void;
  updateEdges: (edges: FlowEdge[]) => void;
  updateNodesAndEdges: (nodes: FlowNode[], edges: FlowEdge[]) => void;
  addNode: (node: FlowNode) => void;
  updateNode: (nodeId: string, updates: Partial<FlowNode>) => void;
  deleteNode: (nodeId: string) => void;
  addEdge: (edge: FlowEdge) => void;
  refreshFlows: () => void;
}

const FlowContext = createContext<FlowContextType | undefined>(undefined);

export function FlowProvider({ children }: { children: ReactNode }) {
  const [flows, setFlows] = useState<FlowMetadata[]>([]);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [activeFlow, setActiveFlowState] = useState<Flow | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const refreshFlows = useCallback(() => {
    setFlows(flowService.getAllFlows());
  }, []);

  const loadActiveFlow = useCallback(() => {
    if (activeFlowId) {
      const flow = flowService.getFlow(activeFlowId);
      setActiveFlowState(flow);
    } else {
      setActiveFlowState(null);
    }
  }, [activeFlowId]);

  useEffect(() => {
    refreshFlows();
    const unsubscribe = flowService.subscribe(refreshFlows);
    return unsubscribe;
  }, [refreshFlows]);

  useEffect(() => {
    loadActiveFlow();
  }, [loadActiveFlow]);

  const setActiveFlow = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    setSelectedNodeId(null);
  }, []);

  const setSelectedNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
  }, []);

  const createFlow = useCallback((name: string, category?: string) => {
    const newFlow = flowService.createFlow(name, category);
    setActiveFlowId(newFlow.id);
    return newFlow;
  }, []);

  const updateFlowName = useCallback((flowId: string, name: string) => {
    flowService.updateFlowName(flowId, name);
    loadActiveFlow();
  }, [loadActiveFlow]);

  const deleteFlow = useCallback((flowId: string) => {
    flowService.deleteFlow(flowId);
    if (activeFlowId === flowId) {
      const remainingFlows = flowService.getAllFlows();
      setActiveFlowId(remainingFlows.length > 0 ? remainingFlows[0].id : null);
    }
  }, [activeFlowId]);

  const updateNodes = useCallback((nodes: FlowNode[]) => {
    if (!activeFlowId) return;
    flowService.updateNodes(activeFlowId, nodes);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const updateEdges = useCallback((edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    flowService.updateEdges(activeFlowId, edges);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const updateNodesAndEdges = useCallback((nodes: FlowNode[], edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    flowService.updateNodesAndEdges(activeFlowId, nodes, edges);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const addNode = useCallback((node: FlowNode) => {
    if (!activeFlowId) return;
    flowService.addNode(activeFlowId, node);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const updateNode = useCallback((nodeId: string, updates: Partial<FlowNode>) => {
    if (!activeFlowId) return;
    flowService.updateNode(activeFlowId, nodeId, updates);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const deleteNode = useCallback((nodeId: string) => {
    if (!activeFlowId) return;
    flowService.deleteNode(activeFlowId, nodeId);
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
    loadActiveFlow();
  }, [activeFlowId, selectedNodeId, loadActiveFlow]);

  const addEdge = useCallback((edge: FlowEdge) => {
    if (!activeFlowId) return;
    flowService.addEdge(activeFlowId, edge);
    loadActiveFlow();
  }, [activeFlowId, loadActiveFlow]);

  const value: FlowContextType = {
    flows,
    activeFlowId,
    activeFlow,
    selectedNodeId,
    setActiveFlow,
    setSelectedNode,
    createFlow,
    updateFlowName,
    deleteFlow,
    updateNodes,
    updateEdges,
    updateNodesAndEdges,
    addNode,
    updateNode,
    deleteNode,
    addEdge,
    refreshFlows
  };

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (context === undefined) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}
