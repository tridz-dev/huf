---
name: frontend-flow-builder
category: ui
---

# Frontend Flow Builder

A visual workflow builder for HUF (Human Usable Flows) that enables users to create, manage, and execute complex automation workflows using a drag-and-drop interface. Built on React Flow with TypeScript and Tailwind CSS.

## Overview

The Flow Builder provides a professional UI for designing automated workflows with various node types and configurations. It supports visual flow editing with real-time updates, node configuration panels, and in-memory flow management.

**Key Capabilities:**
- Visual drag-and-drop canvas for workflow design
- Multiple node types: Triggers, Actions, Utilities, and End nodes
- Real-time connection creation between nodes
- Node configuration via side panels and modals
- Flow versioning and metadata tracking
- In-memory storage with subscription-based updates

## Key Files

| File | Purpose | Description |
|------|---------|-------------|
| `frontend/src/pages/FlowCanvasPage.tsx` | Main page | Route container for the flow builder, manages flow selection from URL params |
| `frontend/src/components/FlowCanvas.tsx` | Canvas component | Core React Flow canvas with node rendering, edge connections, and interaction handling |
| `frontend/src/contexts/FlowContext.tsx` | State management | React Context provider for flow state, node operations, and service integration |
| `frontend/src/services/flowService.ts` | Data service | In-memory flow CRUD operations with Map-based storage and subscription pattern |
| `frontend/src/types/flow.types.ts` | Type definitions | TypeScript interfaces for Flow, FlowNode, FlowEdge, and configuration types |
| `frontend/src/components/nodes/TriggerNode.tsx` | Trigger node | Workflow entry point node with configuration status indicator |
| `frontend/src/components/nodes/ActionNode.tsx` | Action node | Processing step node with icon mapping for different action types |
| `frontend/src/components/nodes/EndNode.tsx` | End node | Workflow termination node with green styling |
| `frontend/src/components/FlowsSidebarContent.tsx` | Flow list | Sidebar component for flow navigation, creation, and categorization |
| `frontend/src/components/RightSidebar.tsx` | Config panel | Resizable right panel for node configuration with form rendering |
| `frontend/src/components/FlowNode.tsx` | Base node | Simple base node component for generic flow visualization |
| `frontend/src/components/modals/NodeSelectionModal.tsx` | Node selector | Comprehensive modal for adding triggers and actions with search and tabs |
| `frontend/src/components/modals/ActionSelectionModal.tsx` | Action selector | Simplified modal for selecting action types by category |
| `frontend/src/components/modals/TriggerConfigModal.tsx` | Trigger config | Modal for configuring trigger settings (webhook, schedule, doc-event) |
| `frontend/src/data/actions.ts` | Action definitions | Static data for available action types with icons and categories |
| `frontend/src/data/triggers.ts` | Trigger definitions | Static data for available trigger types with categorization |

## How It Works

### Data Flow

```
User Interaction
       ↓
FlowCanvas (React Flow events)
       ↓
FlowContext (state operations)
       ↓
flowService (Map storage)
       ↓
Subscribers notified → UI updates
```

### Flow Service Architecture

The `FlowService` class provides in-memory flow management using a Map-based storage system:

```typescript
class FlowService {
  private flows: Map<string, Flow> = new Map();
  private listeners: Set<() => void> = new Set();
  
  // Subscription pattern for reactive updates
  subscribe(listener: () => void): () => void
  
  // CRUD operations
  createFlow(name: string, category?: string): Flow
  updateFlow(id: string, updates: Partial<Flow>): Flow | null
  deleteFlow(id: string): boolean
  
  // Node/Edge operations
  updateNodesAndEdges(flowId: string, nodes: FlowNode[], edges: FlowEdge[])
  addNode(flowId: string, node: FlowNode)
  updateNode(flowId: string, nodeId: string, updates: Partial<FlowNode>)
  deleteNode(flowId: string, nodeId: string)
}
```

### Node Type System

Nodes are rendered using React Flow's custom node type system:

```typescript
// Node type mapping in FlowCanvas.tsx
const nodeTypesWithAddButton = useMemo(
  () => ({
    trigger: (props) => <TriggerNode {...props} onAddNode={handleAddNode} />,
    action: (props) => <ActionNode {...props} onAddNode={handleAddNode} />,
    end: EndNode
  }),
  [handleAddNode]
);
```

Each node type has:
- **Visual representation**: Card-based UI with icon, label, and status
- **Connection handles**: Source (bottom) and target (top) handles for edge connections
- **Add button**: Hover-triggered button to add subsequent nodes
- **Configuration state**: `configured` boolean and type-specific config

### Flow Data Structure

```typescript
interface Flow {
  id: string;                    // Unique flow identifier
  name: string;                  // Display name
  description?: string;          // Optional description
  status: FlowStatus;            // 'draft' | 'active' | 'paused' | 'error'
  category?: string;             // Organization category
  nodes: FlowNode[];             // React Flow nodes with FlowNodeData
  edges: FlowEdge[];             // React Flow edges
  createdAt: Date;
  updatedAt: Date;
  version: number;               // Auto-incremented on changes
}

interface FlowNodeData {
  label: string;                 // Display label
  nodeType: NodeType;            // 'trigger' | 'action' | 'end'
  description?: string;
  icon?: string;                 // Lucide icon name
  configured: boolean;           // Configuration status
  triggerConfig?: TriggerConfig; // Type-specific trigger config
  actionConfig?: ActionConfig;   // Type-specific action config
  status?: 'idle' | 'running' | 'success' | 'error';
}
```

### Adding Nodes Flow

1. **User clicks add button** on a node (or clicks unconfigured trigger)
2. **NodeSelectionModal opens** with mode ('trigger' or 'action')
3. **User selects type** from categorized options
4. **Configuration form renders** based on selected type
5. **On save**:
   - For triggers: Updates existing trigger node config
   - For actions: Creates new action node + edge, reconnects existing edges

### Configuration Persistence

Trigger and action configurations are stored in `FlowNodeData`:

```typescript
// Trigger configurations
interface WebhookTriggerConfig {
  type: 'webhook';
  url?: string;
  apiKey?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
}

interface ScheduleTriggerConfig {
  type: 'schedule';
  intervalType: 'minutes' | 'hours' | 'days' | 'custom';
  interval?: number;
  cronExpression?: string;
}

// Action configurations
interface TransformActionConfig {
  type: 'transform';
  transformations?: Array<{
    sourceField: string;
    targetField: string;
    operation?: 'copy' | 'map' | 'concat' | 'split';
  }>;
}

interface RouterActionConfig {
  type: 'router';
  branches?: Array<{
    id: string;
    name: string;
    condition: string;
  }>;
}
```

## Node Types

### Trigger Nodes

| Type | Icon | Description | Config Fields |
|------|------|-------------|---------------|
| `webhook` | Webhook | HTTP endpoint trigger | url, apiKey, method |
| `schedule` | Clock | Time-based trigger | intervalType, interval, cronExpression |
| `doc-event` | Database | Frappe document event | doctype, event |
| `app-trigger` | Mail | External app integration | integration, event, config |

### Action Nodes

| Type | Icon | Category | Description |
|------|------|----------|-------------|
| `transform` | Repeat | Transform | Data transformation operations |
| `router` | GitBranch | Control | Conditional branching |
| `human-in-loop` | UserCheck | Control | Human approval workflow |
| `loop` | RotateCw | Control | Iterative processing |
| `code` | Code | Transform | Custom code execution |
| `utility-email` | Mail | Utility | Send email |
| `utility-webhook` | Webhook | Utility | HTTP webhook call |
| `utility-file` | FileText | Utility | File operations |
| `utility-date` | Calendar | Utility | Date manipulation |

### End Node

- Fixed green styling with CheckCircle2 icon
- Only target handle (no source handle - terminal node)
- Represents workflow completion

## Extension Points

### Adding a New Node Type

1. **Create node component** in `frontend/src/components/nodes/`:

```typescript
// NewNodeType.tsx
import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { FlowNodeData } from '../../types/flow.types';

interface NewNodeTypeProps extends NodeProps<FlowNodeData> {
  onAddNode?: (sourceNodeId: string) => void;
}

export const NewNodeType = memo(({ id, data, selected, onAddNode }: NewNodeTypeProps) => {
  return (
    <div className="group">
      {/* Target handle for incoming connections */}
      <Handle type="target" position={Position.Top} />
      
      {/* Node card content */}
      <Card className="w-64 p-4">
        {/* Your node UI */}
      </Card>
      
      {/* Source handle for outgoing connections */}
      <Handle type="source" position={Position.Bottom} />
      
      {/* Optional: Add node button */}
      <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100">
        <Button onClick={() => onAddNode?.(id)}>
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
});
```

2. **Register in FlowCanvas**:

```typescript
// In FlowCanvas.tsx, add to nodeTypesWithAddButton
const nodeTypesWithAddButton = useMemo(
  () => ({
    trigger: (props) => <TriggerNode {...props} onAddNode={handleAddNode} />,
    action: (props) => <ActionNode {...props} onAddNode={handleAddNode} />,
    end: EndNode,
    newNodeType: NewNodeType  // Add here
  }),
  [handleAddNode]
);
```

3. **Add type definition** to `flow.types.ts`:

```typescript
export type NodeType =
  | 'trigger'
  | 'action'
  | 'end'
  | 'newNodeType';  // Add here
```

4. **Add configuration type** (if needed):

```typescript
export interface NewNodeTypeConfig {
  type: 'new-node-type';
  // Your config fields
}

export type ActionConfig =
  | // ... existing configs
  | NewNodeTypeConfig;
```

5. **Add to selection modal** (if user-selectable):

```typescript
// In actions.ts or triggers.ts
export const actionOptions: ActionOption[] = [
  // ... existing actions
  {
    id: 'new-node-type',
    name: 'New Node Type',
    description: 'Description of what it does',
    icon: 'IconName',
    category: 'transform'  // or 'control', 'utility', 'integration'
  }
];
```

6. **Handle in modal**:

```typescript
// In NodeSelectionModal.tsx, handleSelectAction method
} else if (actionId === 'new-node-type') {
  config = { type: 'new-node-type', /* defaults */ };
}
```

7. **Add configuration form** in `RightSidebar.tsx`:

```typescript
// In renderTriggerForm or similar method
if (config.type === 'new-node-type') {
  return (
    <div>
      {/* Your configuration form fields */}
    </div>
  );
}
```

### Adding a New Trigger Type

1. Add to `triggerOptions` in `frontend/src/data/triggers.ts`
2. Add config interface to `flow.types.ts`
3. Handle in `handleSelectTrigger` in `NodeSelectionModal.tsx`
4. Add form rendering in `renderTriggerForm` in both `NodeSelectionModal.tsx` and `RightSidebar.tsx`

### Customizing Node Appearance

Nodes use Tailwind CSS with these common patterns:

```typescript
// Selection state
selected ? 'ring-2 ring-primary shadow-lg' : 'shadow-md'

// Configuration state (triggers)
data.configured
  ? 'border-primary bg-primary/5'
  : 'border-amber-500 bg-amber-50'

// Icon container
<div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
  <Icon className="w-5 h-5" />
</div>
```

## Dependencies

### Required Packages

```json
{
  "dependencies": {
    "reactflow": "^11.x",
    "lucide-react": "^0.x",
    "react": "^18.x",
    "react-router-dom": "^6.x"
  }
}
```

### Internal Dependencies

- **UI Components**: `frontend/src/components/ui/` - shadcn/ui components (Card, Button, Input, Select, Dialog, Tabs)
- **Agent Types**: `frontend/src/types/agent.types.ts` - For AI agent integration
- **Mock API**: `frontend/src/services/mockApi.ts` - For agent fetching

### React Flow Integration

Key imports from `reactflow`:
- `ReactFlow` - Main canvas component
- `Background`, `Controls`, `MiniMap` - Canvas controls
- `Handle`, `Position` - Node connection handles
- `addEdge`, `applyNodeChanges`, `applyEdgeChanges` - State updates
- `Node`, `Edge`, `Connection`, `NodeChange`, `EdgeChange` - Type definitions

## Gotchas

### In-Memory Storage

⚠️ **Flows are stored in memory only** - refreshing the page resets to default flows. The `FlowService` initializes with 5 example flows in `initializeDefaultFlows()`. For persistence, implement backend sync in:

```typescript
// In flowService.ts, modify updateFlow to persist:
updateFlow(id: string, updates: Partial<Flow>): Flow | null {
  // ... existing logic
  // TODO: Add API call to save to backend
  // frappe.call({ method: 'huf.ai.flow_api.save_flow_definition', args: { ... } })
}
```

### Node ID Generation

Node IDs use timestamp-based generation which could collide in rapid succession:

```typescript
// Current approach
const newNodeId = `node-${Date.now()}`;

// Safer approach with random suffix
const newNodeId = `node-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
```

### Edge Reconnection on Add

When adding a node between existing nodes, the logic reconnects edges but assumes single outgoing edge:

```typescript
// In handleSelectAction in FlowCanvas.tsx
const targetEdges = edges.filter((e) => e.source === sourceNodeForAction);
const newEdges = edges.filter((e) => e.source !== sourceNodeForAction);
// This removes ALL outgoing edges from source
```

For branching nodes (like Router), this logic needs modification to preserve multiple edges.

### Icon Mapping Maintenance

Icon maps are duplicated across files. Keep them in sync:

- `TriggerNode.tsx` - Trigger icons
- `ActionNode.tsx` - Action icons  
- `NodeSelectionModal.tsx` - Modal icons
- `ActionSelectionModal.tsx` - Modal icons
- `TriggerConfigModal.tsx` - Modal icons

Consider creating a centralized icon registry:

```typescript
// icons.ts
export const nodeIcons = {
  trigger: { Webhook, Clock, Database, Mail },
  action: { Repeat, GitBranch, RotateCw, UserCheck, Code, Mail, Webhook, FileText, Calendar }
};
```

### Flow Context Provider

The FlowContext must wrap any component using `useFlowContext()`:

```typescript
// In App.tsx or layout
<FlowProvider>
  <FlowCanvasPage />
</FlowProvider>
```

Using the hook outside the provider throws:
```
Error: useFlowContext must be used within a FlowProvider
```

### Subscription Cleanup

Always unsubscribe from flow service updates to prevent memory leaks:

```typescript
useEffect(() => {
  const unsubscribe = flowService.subscribe(refreshFlows);
  return unsubscribe;  // Cleanup on unmount
}, [refreshFlows]);
```

### TypeScript Strictness

The frontend enforces strict TypeScript. Common issues:

1. **Unused variables**: Remove or prefix with underscore
2. **Missing type annotations**: Explicitly type callback parameters
3. **Implicit any**: Enable `strict: true` in tsconfig.json

### Canvas Background

The background uses CSS custom properties for theming:

```typescript
<Background 
  variant="dots" 
  gap={16} 
  size={2} 
  color="oklch(var(--muted-foreground) / 0.35)" 
/>
```

Ensure CSS variables are defined in your theme configuration.

### Resizable Sidebar

The `RightSidebar` has a resize handle with document-level event listeners. Ensure cleanup:

```typescript
// Current implementation has a bug - useState instead of useEffect
useState(() => {  // BUG: Should be useEffect
  if (isResizing) {
    document.addEventListener('mousemove', handleMouseMove);
    // ...
  }
});
```

### Modal State Management

The `NodeSelectionModal` handles both trigger and action modes. When using for trigger reconfiguration:

```typescript
// Must pass initialTriggerConfig to pre-select current type
<NodeSelectionModal
  mode="trigger"
  initialTriggerConfig={selectedNode.data.triggerConfig}
  // ...
/>
```

### Flow Versioning

Version auto-increments on every change via `updateFlow`. For manual versioning:

```typescript
// Save major version manually
flowService.updateFlow(flowId, { 
  version: flow.version + 1 
});
```
