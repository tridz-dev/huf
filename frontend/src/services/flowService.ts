import { Flow, FlowMetadata, FlowNode, FlowEdge, FlowStatus } from '../types/flow.types';

class FlowService {
  private flows: Map<string, Flow> = new Map();
  private listeners: Set<() => void> = new Set();

  constructor() {
    this.initializeDefaultFlows();
  }

  private initializeDefaultFlows() {
    const webformFlow: Flow = {
      id: 'flow-1',
      name: 'Webform',
      description: 'Web form trigger flow',
      status: 'active',
      category: 'Uncategorized',
      nodes: [
        {
          id: 'node-1',
          type: 'trigger',
          position: { x: 250, y: 50 },
          data: {
            label: 'Web Form',
            nodeType: 'trigger',
            description: 'Trigger',
            configured: true,
            triggerConfig: {
              type: 'webhook',
              url: 'https://api.example.com/webhook/abc123',
              method: 'POST'
            }
          }
        },
        {
          id: 'node-2',
          type: 'action',
          position: { x: 250, y: 200 },
          data: {
            label: 'Run Agent',
            nodeType: 'action',
            description: 'Action',
            configured: true,
            actionConfig: {
              type: 'transform'
            }
          }
        },
        {
          id: 'node-3',
          type: 'end',
          position: { x: 250, y: 350 },
          data: {
            label: 'End',
            nodeType: 'end',
            description: 'Complete',
            configured: true
          }
        }
      ],
      edges: [
        {
          id: 'edge-1',
          source: 'node-1',
          target: 'node-2',
          type: 'default'
        },
        {
          id: 'edge-2',
          source: 'node-2',
          target: 'node-3',
          type: 'default'
        }
      ],
      createdAt: new Date(),
      updatedAt: new Date(),
      version: 1
    };

    const untitledFlow: Flow = {
      id: 'flow-2',
      name: 'Untitled',
      description: 'New automation flow',
      status: 'draft',
      category: 'Uncategorized',
      nodes: [
        {
          id: 'empty-trigger',
          type: 'trigger',
          position: { x: 250, y: 100 },
          data: {
            label: 'Select Trigger',
            nodeType: 'trigger',
            description: 'Empty Trigger',
            configured: false
          }
        }
      ],
      edges: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      version: 1
    };

    const emailAutomationFlow: Flow = {
      id: 'flow-3',
      name: 'Email Automation',
      description: 'Send automated emails based on triggers',
      status: 'active',
      category: 'Automation',
      nodes: [
        {
          id: 'node-1',
          type: 'trigger',
          position: { x: 250, y: 50 },
          data: {
            label: 'Schedule',
            nodeType: 'trigger',
            icon: 'Clock',
            configured: true,
            triggerConfig: {
              type: 'schedule',
              intervalType: 'hours',
              interval: 24
            }
          }
        },
        {
          id: 'node-2',
          type: 'action',
          position: { x: 250, y: 200 },
          data: {
            label: 'Send Email',
            nodeType: 'action',
            icon: 'Mail',
            configured: true,
            actionConfig: {
              type: 'utility-email'
            }
          }
        },
        {
          id: 'node-3',
          type: 'end',
          position: { x: 250, y: 350 },
          data: {
            label: 'End',
            nodeType: 'end',
            configured: true
          }
        }
      ],
      edges: [
        {
          id: 'edge-1',
          source: 'node-1',
          target: 'node-2',
          type: 'default'
        },
        {
          id: 'edge-2',
          source: 'node-2',
          target: 'node-3',
          type: 'default'
        }
      ],
      createdAt: new Date('2025-10-15'),
      updatedAt: new Date('2025-10-28'),
      version: 3
    };

    const slackIntegrationFlow: Flow = {
      id: 'flow-4',
      name: 'Slack Notification',
      description: 'Send notifications to Slack channel',
      status: 'active',
      category: 'Integration',
      nodes: [
        {
          id: 'node-1',
          type: 'trigger',
          position: { x: 250, y: 50 },
          data: {
            label: 'Webhook',
            nodeType: 'trigger',
            icon: 'Webhook',
            configured: true,
            triggerConfig: {
              type: 'webhook',
              method: 'POST'
            }
          }
        },
        {
          id: 'node-2',
          type: 'action',
          position: { x: 250, y: 200 },
          data: {
            label: 'Transform Data',
            nodeType: 'action',
            icon: 'Repeat',
            configured: true,
            actionConfig: {
              type: 'transform'
            }
          }
        },
        {
          id: 'node-3',
          type: 'action',
          position: { x: 250, y: 350 },
          data: {
            label: 'Call Webhook',
            nodeType: 'action',
            icon: 'Webhook',
            configured: true,
            actionConfig: {
              type: 'utility-webhook'
            }
          }
        },
        {
          id: 'node-4',
          type: 'end',
          position: { x: 250, y: 500 },
          data: {
            label: 'End',
            nodeType: 'end',
            configured: true
          }
        }
      ],
      edges: [
        {
          id: 'edge-1',
          source: 'node-1',
          target: 'node-2',
          type: 'default'
        },
        {
          id: 'edge-2',
          source: 'node-2',
          target: 'node-3',
          type: 'default'
        },
        {
          id: 'edge-3',
          source: 'node-3',
          target: 'node-4',
          type: 'default'
        }
      ],
      createdAt: new Date('2025-10-20'),
      updatedAt: new Date('2025-10-27'),
      version: 2
    };

    const dataProcessingFlow: Flow = {
      id: 'flow-5',
      name: 'Data Processing Pipeline',
      description: 'Process and transform incoming data',
      status: 'paused',
      category: 'Automation',
      nodes: [
        {
          id: 'node-1',
          type: 'trigger',
          position: { x: 250, y: 50 },
          data: {
            label: 'Doc Event',
            nodeType: 'trigger',
            icon: 'Database',
            configured: true,
            triggerConfig: {
              type: 'doc-event'
            }
          }
        },
        {
          id: 'node-2',
          type: 'action',
          position: { x: 250, y: 200 },
          data: {
            label: 'Execute Code',
            nodeType: 'action',
            icon: 'Code',
            configured: true,
            actionConfig: {
              type: 'code'
            }
          }
        },
        {
          id: 'node-3',
          type: 'end',
          position: { x: 250, y: 350 },
          data: {
            label: 'End',
            nodeType: 'end',
            configured: true
          }
        }
      ],
      edges: [
        {
          id: 'edge-1',
          source: 'node-1',
          target: 'node-2',
          type: 'default'
        },
        {
          id: 'edge-2',
          source: 'node-2',
          target: 'node-3',
          type: 'default'
        }
      ],
      createdAt: new Date('2025-09-25'),
      updatedAt: new Date('2025-10-10'),
      version: 1
    };

    this.flows.set(webformFlow.id, webformFlow);
    this.flows.set(untitledFlow.id, untitledFlow);
    this.flows.set(emailAutomationFlow.id, emailAutomationFlow);
    this.flows.set(slackIntegrationFlow.id, slackIntegrationFlow);
    this.flows.set(dataProcessingFlow.id, dataProcessingFlow);
  }

  private notifyListeners() {
    this.listeners.forEach(listener => listener());
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getAllFlows(): FlowMetadata[] {
    return Array.from(this.flows.values()).map(flow => ({
      id: flow.id,
      name: flow.name,
      description: flow.description,
      status: flow.status,
      category: flow.category,
      nodeCount: flow.nodes.length,
      createdAt: flow.createdAt,
      updatedAt: flow.updatedAt
    }));
  }

  getFlow(id: string): Flow | null {
    return this.flows.get(id) || null;
  }

  createFlow(name: string, category?: string): Flow {
    const newFlow: Flow = {
      id: `flow-${Date.now()}`,
      name,
      description: 'New automation flow',
      status: 'draft',
      category: category || 'Uncategorized',
      nodes: [
        {
          id: 'empty-trigger',
          type: 'trigger',
          position: { x: 250, y: 100 },
          data: {
            label: 'Select Trigger',
            nodeType: 'trigger',
            description: 'Empty Trigger',
            configured: false
          }
        }
      ],
      edges: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      version: 1
    };

    this.flows.set(newFlow.id, newFlow);
    this.notifyListeners();
    return newFlow;
  }

  updateFlow(id: string, updates: Partial<Flow>): Flow | null {
    const flow = this.flows.get(id);
    if (!flow) return null;

    const updatedFlow = {
      ...flow,
      ...updates,
      updatedAt: new Date(),
      version: flow.version + 1
    };

    this.flows.set(id, updatedFlow);
    this.notifyListeners();
    return updatedFlow;
  }

  deleteFlow(id: string): boolean {
    const deleted = this.flows.delete(id);
    if (deleted) {
      this.notifyListeners();
    }
    return deleted;
  }

  updateFlowName(id: string, name: string): Flow | null {
    return this.updateFlow(id, { name });
  }

  updateFlowStatus(id: string, status: FlowStatus): Flow | null {
    return this.updateFlow(id, { status });
  }

  updateNodes(flowId: string, nodes: FlowNode[]): Flow | null {
    return this.updateFlow(flowId, { nodes });
  }

  updateEdges(flowId: string, edges: FlowEdge[]): Flow | null {
    return this.updateFlow(flowId, { edges });
  }

  updateNodesAndEdges(flowId: string, nodes: FlowNode[], edges: FlowEdge[]): Flow | null {
    return this.updateFlow(flowId, { nodes, edges });
  }

  addNode(flowId: string, node: FlowNode): Flow | null {
    const flow = this.flows.get(flowId);
    if (!flow) return null;

    const updatedNodes = [...flow.nodes, node];
    return this.updateNodes(flowId, updatedNodes);
  }

  updateNode(flowId: string, nodeId: string, updates: Partial<FlowNode>): Flow | null {
    const flow = this.flows.get(flowId);
    if (!flow) return null;

    const updatedNodes = flow.nodes.map(node =>
      node.id === nodeId ? { ...node, ...updates } : node
    );

    return this.updateNodes(flowId, updatedNodes);
  }

  deleteNode(flowId: string, nodeId: string): Flow | null {
    const flow = this.flows.get(flowId);
    if (!flow) return null;

    const updatedNodes = flow.nodes.filter(node => node.id !== nodeId);
    const updatedEdges = flow.edges.filter(
      edge => edge.source !== nodeId && edge.target !== nodeId
    );

    return this.updateNodesAndEdges(flowId, updatedNodes, updatedEdges);
  }

  addEdge(flowId: string, edge: FlowEdge): Flow | null {
    const flow = this.flows.get(flowId);
    if (!flow) return null;

    const updatedEdges = [...flow.edges, edge];
    return this.updateEdges(flowId, updatedEdges);
  }
}

export const flowService = new FlowService();
