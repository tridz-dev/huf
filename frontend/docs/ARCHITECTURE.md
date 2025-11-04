# Flow Builder Architecture

## Overview

This is an enterprise-grade flow builder application built with React, TypeScript, and React Flow. The architecture is designed to be modular, scalable, and maintainable as the application grows.

## Core Architecture Layers

### 1. Type System (`src/types/`)
- **flow.types.ts**: Comprehensive TypeScript interfaces for flows, nodes, triggers, actions, and configurations
- **modal.types.ts**: Types for modal interactions and UI components

### 2. Services Layer (`src/services/`)
- **flowService.ts**: In-memory data storage with subscription-based updates
  - Manages CRUD operations for flows
  - Provides observable pattern for real-time UI updates
  - Can be easily swapped for Supabase or other backends

### 3. State Management (`src/contexts/`)
- **FlowContext.tsx**: Global state for flows, active flow, and node operations
- **ModalContext.tsx**: State management for modal dialogs

### 4. Data Layer (`src/data/`)
- **triggers.ts**: Trigger type definitions and metadata
- **actions.ts**: Action type definitions and metadata

### 5. Components

#### Layout Components
- **App.tsx**: Root component with provider wrappers
- **Header.tsx**: Top navigation bar
- **LeftSidebar.tsx**: Flow management sidebar with multi-flow support
- **RightSidebar.tsx**: Node configuration panel
- **FlowCanvas.tsx**: Main React Flow canvas

#### Node Components (`src/components/nodes/`)
- **TriggerNode.tsx**: Visual representation of trigger nodes
- **ActionNode.tsx**: Visual representation of action nodes with add button
- **EndNode.tsx**: Visual representation of end nodes

#### Modal Components (`src/components/modals/`)
- **TriggerConfigModal.tsx**: Comprehensive trigger configuration with tabs
- **ActionSelectionModal.tsx**: Action selection with categorized options

## Data Flow

1. **Initialization**
   - FlowService initializes with default flows
   - FlowProvider wraps the app and subscribes to service updates
   - Active flow is loaded and displayed

2. **Flow Switching**
   - User clicks flow in LeftSidebar
   - FlowContext updates activeFlowId
   - FlowCanvas receives new nodes/edges from activeFlow
   - React Flow renders the updated graph

3. **Node Configuration**
   - User clicks unconfigured trigger node
   - TriggerConfigModal opens with node ID
   - User selects trigger type and fills form
   - Config saved to node via FlowContext
   - FlowService updates in-memory storage
   - Canvas re-renders with updated node

4. **Adding Actions**
   - User hovers over action node, sees plus button
   - User clicks plus button
   - ActionSelectionModal opens
   - User selects action type
   - New node created and inserted between source and targets
   - Edges automatically reconnected
   - Canvas updates via React Flow

## State Management Pattern

### Context API Usage
- **FlowContext**: Manages flow data and operations
  - Provides flows list, active flow, selected node
  - Exposes CRUD operations for flows and nodes
  - Automatically syncs with FlowService

- **ModalContext**: Manages modal state
  - Controls open/close state
  - Passes configuration callbacks
  - Decouples modal logic from components

### Observable Pattern
- FlowService implements subscription pattern
- Components subscribe via useEffect
- Automatic updates when data changes
- Clean unsubscribe on unmount

## Node System

### Node Types
1. **Trigger**: Entry point of flow
2. **Action**: Processing step
3. **End**: Terminal node

### Node Data Structure
```typescript
interface FlowNodeData {
  label: string;
  nodeType: NodeType;
  description?: string;
  icon?: string;
  configured: boolean;
  triggerConfig?: TriggerConfig;
  actionConfig?: ActionConfig;
  status?: 'idle' | 'running' | 'success' | 'error';
}
```

### Configuration Types
- **Trigger**: webhook, schedule, doc-event, app-trigger
- **Action**: transform, router, loop, human-in-loop, code, utilities

## React Flow Integration

### Custom Nodes
- Each node type has custom React component
- Nodes display configuration status
- Interactive elements (click to configure, add button)
- Visual feedback for selected state

### Edge Management
- Automatic edge creation via plus button
- Edge reconnection when inserting nodes
- Validation to prevent cycles

### Canvas Features
- Pan and zoom
- MiniMap for navigation
- Background grid
- Fit view on load
- Controls panel

## Extensibility

### Adding New Trigger Types
1. Add type to `TriggerType` in flow.types.ts
2. Create config interface extending base config
3. Add entry to `triggerOptions` in triggers.ts
4. Add form section in TriggerConfigModal
5. Update icon mapping

### Adding New Action Types
1. Add type to `ActionType` in flow.types.ts
2. Create config interface
3. Add entry to `actionOptions` in actions.ts
4. Add form in ActionSelectionModal
5. Update icon and label mappings

### Replacing In-Memory Storage with Supabase
1. Create Supabase tables matching Flow interface
2. Replace FlowService methods with Supabase queries
3. Use Supabase realtime subscriptions
4. Keep same service interface for zero component changes

## UI/UX Features

### Multi-Flow Management
- Create/rename/delete flows
- Visual status indicators
- Categorized organization
- Active flow highlighting

### Node Configuration
- Click empty trigger to configure
- Right sidebar shows selected node config
- Modal-based configuration forms
- JSON preview of configuration

### Node Addition
- Hover plus button on action nodes
- Modal selection of action type
- Automatic insertion with edge reconnection
- Smart positioning

### Visual Feedback
- Selected node highlighting
- Configured/unconfigured states
- Status indicators (draft, active, error)
- Smooth transitions and animations

## Performance Considerations

- React Flow handles large graphs efficiently
- Memoized node components prevent unnecessary re-renders
- Subscription pattern minimizes prop drilling
- Lazy loading of modals
- Virtualized node rendering via React Flow

## Future Enhancements

### Planned Features
1. **Execution Engine**: Run flows client-side or server-side
2. **Version Control**: Flow versioning and rollback
3. **Collaboration**: Real-time multi-user editing
4. **Templates**: Pre-built flow templates
5. **Variables**: Data passing between nodes
6. **Conditional Routing**: Branch logic in router nodes
7. **Loop Support**: Iterate over arrays
8. **Error Handling**: Try-catch blocks and retries
9. **Testing**: Flow testing and debugging tools
10. **Export/Import**: Save and load flows as JSON

### Technical Debt
- Add comprehensive unit tests
- Add E2E tests with Playwright
- Implement undo/redo functionality
- Add keyboard shortcuts
- Improve accessibility (ARIA labels)
- Add drag-and-drop from sidebar to canvas
- Implement context menus on nodes
- Add bulk operations

## Development Guidelines

### Code Organization
- One component per file
- Co-locate related utilities with components
- Keep files under 300 lines
- Extract reusable logic to hooks
- Use TypeScript strictly

### Naming Conventions
- PascalCase for components
- camelCase for functions and variables
- UPPER_SNAKE_CASE for constants
- Prefix custom hooks with `use`
- Suffix context providers with `Provider`

### State Management
- Use Context for global state
- Use local state for UI-only state
- Prefer derived state over stored state
- Keep state as close to usage as possible

### TypeScript Usage
- Define interfaces for all data structures
- Use union types for variants
- Prefer interfaces over types
- Use generics for reusable components
- Avoid `any` type

## Testing Strategy

### Unit Tests
- Test service layer methods
- Test context providers
- Test utility functions
- Mock dependencies

### Integration Tests
- Test component interactions
- Test modal flows
- Test node operations
- Test edge cases

### E2E Tests
- Test complete user flows
- Test multi-flow scenarios
- Test configuration workflows
- Test error states
