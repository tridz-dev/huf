import { useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, Search, Wrench } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { getAgents } from '@/services/agentApi';
import { attachServiceTools, getServiceTools } from '@/services/integrationApi';
import type { AgentDoc } from '@/types/agent.types';
import type { ServiceTool } from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface AddIntegrationToAgentModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  service: string;
  integrationName?: string;
}

export function AddIntegrationToAgentModal({
  open,
  onOpenChange,
  service,
  integrationName,
}: AddIntegrationToAgentModalProps) {
  const [tools, setTools] = useState<ServiceTool[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [selectedToolNames, setSelectedToolNames] = useState<Set<string>>(new Set());
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [selectedAgentNames, setSelectedAgentNames] = useState<Set<string>>(new Set());
  const [agentSearch, setAgentSearch] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setSelectedAgentNames(new Set());
      setSelectedToolNames(new Set());
      setAgentSearch('');
      return;
    }

    setToolsLoading(true);
    setAgentsLoading(true);

    getServiceTools(service)
      .then((items) => {
        setTools(items || []);
        // Every tool is selected by default — most users want the full set,
        // but can now deselect the ones they don't need for this agent.
        setSelectedToolNames(new Set((items || []).map((t) => t.tool_name)));
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load tools');
      })
      .finally(() => setToolsLoading(false));

    getAgents()
      .then((result) => {
        const list = Array.isArray(result) ? result : result.items;
        setAgents(list || []);
      })
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load agents');
      })
      .finally(() => setAgentsLoading(false));
  }, [open, service]);

  const filteredAgents = useMemo(() => {
    const query = agentSearch.trim().toLowerCase();
    if (!query) return agents;
    return agents.filter(
      (agent) =>
        (agent.agent_name || '').toLowerCase().includes(query) ||
        (agent.name || '').toLowerCase().includes(query),
    );
  }, [agents, agentSearch]);

  const toggleTool = (name: string) => {
    setSelectedToolNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const handleSelectAllTools = () => {
    if (selectedToolNames.size === tools.length) {
      setSelectedToolNames(new Set());
    } else {
      setSelectedToolNames(new Set(tools.map((t) => t.tool_name)));
    }
  };

  const toggleAgent = (name: string) => {
    setSelectedAgentNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedAgentNames.size === filteredAgents.length) {
      setSelectedAgentNames(new Set());
    } else {
      setSelectedAgentNames(new Set(filteredAgents.map((a) => a.name)));
    }
  };

  const handleSubmit = async () => {
    if (selectedAgentNames.size === 0) {
      toast.error('Select at least one agent');
      return;
    }
    if (selectedToolNames.size === 0) {
      toast.error('Select at least one tool');
      return;
    }

    setSubmitting(true);
    try {
      const result = await attachServiceTools({
        service,
        tool_names: Array.from(selectedToolNames),
        agents: Array.from(selectedAgentNames),
      });

      const { attached_to_agents = 0, skipped = 0, errors = [] } = result;

      if (errors.length > 0) {
        toast.error(`Attached to ${attached_to_agents} agents, ${errors.length} failed`, {
          description: errors.slice(0, 3).join('; '),
        });
      } else {
        toast.success(
          `Added ${selectedToolNames.size} tool${selectedToolNames.size > 1 ? 's' : ''} to ${selectedAgentNames.size} agent${
            selectedAgentNames.size > 1 ? 's' : ''
          }${skipped > 0 ? ` (${skipped} already present)` : ''}`,
        );
      }

      onOpenChange(false);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to attach tools');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="sm:max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5" />
            Add to Agent
          </DialogTitle>
          <DialogDescription>
            Attach the <span className="font-medium">{service}</span> tools to one or more agents.
            {integrationName ? ` Integration: ${integrationName}` : ''}
          </DialogDescription>
        </DialogScrollHeader>

        <div className="space-y-6 px-6 py-2">
          {/* Tools selection */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-steel">
                <Wrench className="w-4 h-4" />
                Tools to attach
                <Badge variant="outline" className="ml-1">
                  {selectedToolNames.size}/{tools.length}
                </Badge>
              </div>
              {tools.length > 0 && (
                <Button variant="ghost" size="sm" onClick={handleSelectAllTools}>
                  {selectedToolNames.size === tools.length ? 'Deselect all' : 'Select all'}
                </Button>
              )}
            </div>
            {toolsLoading ? (
              <div className="flex items-center gap-2 text-sm text-steel-soft">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading tools...
              </div>
            ) : tools.length === 0 ? (
              <div className="text-sm text-steel-soft">No tools found for this service.</div>
            ) : (
              <div className="rounded-md border border-border divide-y divide-border max-h-52 overflow-y-auto">
                {tools.map((tool) => {
                  const selected = selectedToolNames.has(tool.tool_name);
                  return (
                    <label
                      key={tool.tool_name}
                      className={`flex items-start gap-3 p-3 cursor-pointer hover:bg-muted/50 transition-colors ${
                        selected ? 'bg-muted/50' : ''
                      }`}
                    >
                      <Checkbox
                        checked={selected}
                        onCheckedChange={() => toggleTool(tool.tool_name)}
                        className="mt-0.5"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-sm truncate">{tool.tool_name}</div>
                        <div className="text-xs text-steel-soft">{tool.description}</div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* Agent selection */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-steel">
                <Bot className="w-4 h-4" />
                Select agents
                <Badge variant="outline" className="ml-1">
                  {selectedAgentNames.size}
                </Badge>
              </div>
              {filteredAgents.length > 0 && (
                <Button variant="ghost" size="sm" onClick={handleSelectAll}>
                  {selectedAgentNames.size === filteredAgents.length ? 'Deselect all' : 'Select all'}
                </Button>
              )}
            </div>

            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
              <Input
                placeholder="Search agents..."
                value={agentSearch}
                onChange={(e) => setAgentSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            {agentsLoading ? (
              <div className="flex items-center gap-2 text-sm text-steel-soft py-4">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading agents...
              </div>
            ) : filteredAgents.length === 0 ? (
              <div className="text-sm text-steel-soft py-4 text-center">No agents found.</div>
            ) : (
              <div className="rounded-md border border-border divide-y divide-border max-h-64 overflow-y-auto">
                {filteredAgents.map((agent) => {
                  const selected = selectedAgentNames.has(agent.name);
                  return (
                    <label
                      key={agent.name}
                      className={`flex items-start gap-3 p-3 cursor-pointer hover:bg-muted/50 transition-colors ${
                        selected ? 'bg-muted/50' : ''
                      }`}
                    >
                      <Checkbox
                        checked={selected}
                        onCheckedChange={() => toggleAgent(agent.name)}
                        className="mt-0.5"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">
                          {agent.agent_name || agent.name}
                        </div>
                        {agent.description && (
                          <div className="text-xs text-steel-soft truncate">{agent.description}</div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <DialogScrollFooter className="items-center justify-between sm:justify-between">
          <div className="text-sm text-steel-soft">
            {selectedAgentNames.size > 0 ? (
              <>
                {selectedAgentNames.size} agent{selectedAgentNames.size > 1 ? 's' : ''} selected
              </>
            ) : (
              'Select agents to continue'
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={selectedAgentNames.size === 0 || selectedToolNames.size === 0 || submitting}
            >
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Add to {selectedAgentNames.size > 0 ? `${selectedAgentNames.size} Agent${selectedAgentNames.size > 1 ? 's' : ''}` : 'Agent'}
            </Button>
          </div>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
