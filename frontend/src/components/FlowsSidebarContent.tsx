import { useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Workflow, Database, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export function FlowsSidebarContent() {
  const { flows, activeFlowId, setActiveFlow, createFlow, deleteFlow, updateFlowName } = useFlowContext();
  const navigate = useNavigate();
  const [flowsExpanded, setFlowsExpanded] = useState(true);
  const [tablesExpanded, setTablesExpanded] = useState(false);

  const handleCreateFlow = async () => {
    try {
      const newFlow = await createFlow('New Flow', 'Uncategorized');
      navigate(`/flows/${newFlow.id}`);
    } catch (err) {
      toast.error('Failed to create flow', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const handleRenameFlow = async (id: string, currentName: string) => {
    const next = window.prompt('Rename flow', currentName);
    if (!next || next.trim() === '' || next === currentName) return;
    try {
      await updateFlowName(id, next.trim());
      toast.success('Flow renamed');
    } catch (err) {
      toast.error('Failed to rename flow', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const handleDeleteFlow = async (id: string, name: string) => {
    const confirmed = window.confirm(`Delete flow "${name}"? This cannot be undone.`);
    if (!confirmed) return;

    try {
      await deleteFlow(id);
      toast.success('Flow deleted');
      // If we were on this flow's canvas, navigate back to list
      if (activeFlowId === id) {
        navigate('/flows');
      }
    } catch (err) {
      toast.error('Failed to delete flow', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const groupedFlows = flows.reduce((acc, flow) => {
    const category = flow.category || 'Uncategorized';
    if (!acc[category]) acc[category] = [];
    acc[category].push(flow);
    return acc;
  }, {} as Record<string, typeof flows>);

  return (
    <>
      <div className="mb-4">
        <Button
          variant="ghost"
          className="h-auto w-full items-center justify-start gap-2 px-2 py-1.5 text-sm font-normal text-sidebar-foreground hover:bg-panel hover:text-ink"
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
            className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:bg-panel hover:text-ink"
            onClick={(e) => {
              e.stopPropagation();
              handleCreateFlow();
            }}
          >
            <Plus className="w-3 h-3" />
          </Button>
        </Button>
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
                    <Button
                      variant="ghost"
                      className={`h-auto flex-1 justify-start rounded-md px-2 py-1.5 text-sm font-normal text-sidebar-foreground text-left ${
                        activeFlowId === flow.id
                          ? 'bg-panel text-ink border-l-2 border-signal'
                          : 'hover:bg-panel hover:text-ink'
                      }`}
                      onClick={() => setActiveFlow(flow.id)}
                    >
                      <div className="flex w-full items-center gap-2">
                        <span className="flex-1 truncate">{flow.name}</span>
                        <span
                          className={`h-2 w-2 rounded-full ${
                            flow.status === 'active'
                              ? 'bg-good'
                              : flow.status === 'error'
                              ? 'bg-signal'
                              : 'bg-steel-soft'
                          }`}
                        />
                      </div>
                    </Button>
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
                        <DropdownMenuItem
                          onClick={() => handleRenameFlow(flow.id, flow.name)}
                        >
                          <Pencil className="w-3 h-3 mr-2" />
                          Rename
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => handleDeleteFlow(flow.id, flow.name)}
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
        <Button
          variant="ghost"
          className="h-auto w-full items-center justify-start gap-2 px-2 py-1.5 text-sm font-normal text-sidebar-foreground hover:bg-panel hover:text-ink"
          onClick={() => setTablesExpanded(!tablesExpanded)}
        >
          {tablesExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <Database className="w-4 h-4" />
          <span className="flex-1 text-left">Data</span>
        </Button>
                {tablesExpanded && (
                  <div className="ml-6 mt-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full justify-start text-xs hover:bg-panel hover:text-ink"
                      disabled
                    >
                      <Plus className="w-3 h-3 mr-1" />
                      New data (coming soon)
                    </Button>
                  </div>
                )}
      </div>
    </>
  );
}
