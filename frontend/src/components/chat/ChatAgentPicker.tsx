import { useState, useEffect, useMemo } from 'react';
import { CheckIcon, Plus } from 'lucide-react';
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorName,
  ModelSelectorTrigger,
} from '@/components/ai-elements/model-selector';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getChatAgents, type ChatAgentItem } from '@/services/agentApi';
import ChatAvatar from './ChatAvatar';
import { getInitials } from '@/utils/getInitials';
import { DEFAULT_AGENT_COLOR } from '@/data/color';

interface ChatAgentPickerProps {
  value?: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
  showLabel?: boolean;
  label?: string;
}

export function ChatAgentPicker({
  value,
  onValueChange,
  disabled,
  showLabel = false,
  label = 'New chat',
}: ChatAgentPickerProps) {
  const [open, setOpen] = useState(false);
  const [agents, setAgents] = useState<ChatAgentItem[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [agentSearch, setAgentSearch] = useState('');

  // Load agents when the picker opens so the list is fresh.
  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setAgentsLoading(true);

    getChatAgents()
      .then((data) => {
        if (!cancelled) setAgents(data);
      })
      .finally(() => {
        if (!cancelled) setAgentsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setAgentSearch('');
    }
  }, [open]);

  const filteredAgents = useMemo(() => {
    const q = agentSearch.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter(
      (a) =>
        (a.agent_name || a.name).toLowerCase().includes(q) ||
        (a.description ?? '').toLowerCase().includes(q) ||
        (a.model ?? '').toLowerCase().includes(q)
    );
  }, [agents, agentSearch]);

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        <Button
          type="button"
          size={showLabel ? 'default' : 'icon'}
          variant="ghost"
          disabled={disabled}
          data-testid="chat-agent-picker-trigger"
          className={cn(
            'text-steel hover:bg-paper-deep hover:text-ink',
            showLabel && 'gap-2'
          )}
        >
          <Plus className={showLabel ? 'w-4 h-4' : 'w-5 h-5'} />
          {showLabel && <span>{label}</span>}
        </Button>
      </ModelSelectorTrigger>

      <ModelSelectorContent shouldFilter={false} title="Start a new chat" className="max-h-[80vh] overflow-hidden">
        <ModelSelectorInput
          placeholder="Search agents..."
          searchValue={agentSearch}
          onSearchChange={setAgentSearch}
        />

        <ModelSelectorList className="max-h-[60vh] overflow-y-auto">
          {agentsLoading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Loading agents...
            </div>
          ) : filteredAgents.length === 0 ? (
            <ModelSelectorEmpty>No agents found.</ModelSelectorEmpty>
          ) : (
            <ModelSelectorGroup heading="Agents">
              {filteredAgents.map((agent) => (
                <ModelSelectorItem
                  key={agent.name}
                  className="gap-3 px-3 py-2.5"
                  data-testid="chat-agent-picker-item"
                  onSelect={() => {
                    onValueChange(agent.name);
                    setOpen(false);
                  }}
                  value={agent.name}
                >
                  <ChatAvatar
                    variant="listing_ai"
                    color={agent.agent_color || DEFAULT_AGENT_COLOR}
                  >
                    {getInitials(agent.agent_name || agent.name)}
                  </ChatAvatar>

                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <ModelSelectorName>{agent.agent_name || agent.name}</ModelSelectorName>
                    <span className="text-xs text-muted-foreground truncate">
                      {agent.description || agent.model || 'Chat agent'}
                    </span>
                  </div>

                  {value === agent.name ? (
                    <CheckIcon className="ml-auto size-4 shrink-0" />
                  ) : (
                    <div className="ml-auto size-4 shrink-0" />
                  )}
                </ModelSelectorItem>
              ))}
            </ModelSelectorGroup>
          )}
        </ModelSelectorList>
      </ModelSelectorContent>
    </ModelSelector>
  );
}
