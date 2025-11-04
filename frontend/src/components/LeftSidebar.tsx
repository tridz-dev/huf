import { useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Workflow, Database, User, PanelLeftClose, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface LeftSidebarProps {
  onToggle: () => void;
}

export function LeftSidebar({ onToggle }: LeftSidebarProps) {
  const { flows, activeFlowId, setActiveFlow, createFlow, deleteFlow } = useFlowContext();
  const [flowsExpanded, setFlowsExpanded] = useState(true);
  const [tablesExpanded, setTablesExpanded] = useState(false);

  const handleCreateFlow = () => {
    createFlow('New Flow', 'Uncategorized');
  };

  const groupedFlows = flows.reduce((acc, flow) => {
    const category = flow.category || 'Uncategorized';
    if (!acc[category]) acc[category] = [];
    acc[category].push(flow);
    return acc;
  }, {} as Record<string, typeof flows>);

  return (
    <div className="w-60 h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      <div className="p-4 border-b border-sidebar-border">
        <h2 className="text-sm font-semibold text-sidebar-foreground">HufAI</h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          <div className="mb-4">
            <button
              className="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md"
              onClick={() => setFlowsExpanded(!flowsExpanded)}
            >
              {flowsExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
              <Workflow className="w-4 h-4" />
              <span className="flex-1 text-left">Flows</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:bg-sidebar-accent"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCreateFlow();
                }}
              >
                <Plus className="w-3 h-3" />
              </Button>
            </button>
            {flowsExpanded && (
              <div className="ml-6 mt-1 space-y-0.5">
                {Object.entries(groupedFlows).map(([category, categoryFlows]) => (
                  <div key={category}>
                    <div className="text-xs text-muted-foreground px-2 py-1">{category}</div>
                    {categoryFlows.map((flow) => (
                      <div
                        key={flow.id}
                        className="group flex items-center gap-1"
                      >
                        <button
                          className={`flex-1 px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md text-left transition-colors ${
                            activeFlowId === flow.id ? 'bg-sidebar-accent' : ''
                          }`}
                          onClick={() => setActiveFlow(flow.id)}
                        >
                          <div className="flex items-center gap-2">
                            <span className="flex-1 truncate">{flow.name}</span>
                            <span
                              className={`h-2 w-2 rounded-full ${
                                flow.status === 'active'
                                  ? 'bg-green-500'
                                  : flow.status === 'error'
                                  ? 'bg-red-500'
                                  : 'bg-gray-400'
                              }`}
                            />
                          </div>
                        </button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100"
                            >
                              <MoreHorizontal className="w-3 h-3" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem>
                              <Pencil className="w-3 h-3 mr-2" />
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => deleteFlow(flow.id)}
                            >
                              <Trash2 className="w-3 h-3 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <button
              className="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent rounded-md"
              onClick={() => setTablesExpanded(!tablesExpanded)}
            >
              {tablesExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
              <Database className="w-4 h-4" />
              <span className="flex-1 text-left">Data</span>
            </button>
            {tablesExpanded && (
              <div className="ml-6 mt-2">
                <Button variant="ghost" size="sm" className="w-full justify-start text-xs">
                  <Plus className="w-3 h-3 mr-1" />
                  New Data
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <User className="w-4 h-4 text-primary-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-sidebar-foreground truncate">Safwan Erooth</div>
            <div className="text-xs text-muted-foreground truncate">hey@tridz.com</div>
          </div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onToggle}>
            <PanelLeftClose className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
