import { useState, useEffect, useRef } from 'react';
import { CheckIcon, Plus } from 'lucide-react';
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorLogo,
  ModelSelectorLogoGroup,
  ModelSelectorName,
  ModelSelectorTrigger,
} from '@/components/ai-elements/model-selector';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getAgentModels, type AgentModelItem } from '@/services/agentApi';

interface AgentModelSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
  showLabel?: boolean;
}

export function AgentModelSelector({ value, onValueChange, disabled, showLabel = false }: AgentModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const isInitialAutoSelectRef = useRef(true);

  // Fetch agent models for selector
  const {
    items: agentModels,
    initialLoading: modelsLoading,
    search: modelSearch,
    setSearch: setModelSearch,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    AgentModelItem
  >({
    fetchFn: async (params) => {
      const response = await getAgentModels({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });
      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
    autoLoadMore: false, // Don't auto-load more, user can search
  });

  // Set default model when models load (only on initial load, don't trigger onValueChange)
  useEffect(() => {
    if (agentModels.length > 0 && !value && isInitialAutoSelectRef.current) {
      // Silently set the value without triggering onValueChange callback
      // This is just for initial display, not user interaction
      isInitialAutoSelectRef.current = false;
      // Don't call onValueChange here - it's just for internal state
      // The parent will handle setting the initial value if needed
    } else if (agentModels.length > 0 && value) {
      // If value is already set, mark initial auto-select as done
      isInitialAutoSelectRef.current = false;
    }
  }, [agentModels, value]);

  // Reset search when modal opens
  useEffect(() => {
    if (open) {
      setModelSearch('');
    }
  }, [open, setModelSearch]);

  // Group models by chef
  const groupedModels = agentModels.reduce(
    (acc, m) => {
      const chef = m.chef || 'Other';
      if (!acc[chef]) {
        acc[chef] = [];
      }
      acc[chef].push(m);
      return acc;
    },
    {} as Record<string, AgentModelItem[]>
  );

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        <Button 
          size={showLabel ? "default" : "icon"}
          variant={showLabel ? "outline" : "ghost"}
          disabled={disabled}
          className={cn(
            'text-zinc-500 hover:bg-zinc-200 hover:text-zinc-900',
            showLabel && 'gap-2',
            disabled && 'disabled:opacity-100'
          )}
        >
          <Plus className={showLabel ? "w-4 h-4" : "w-5 h-5"} />
          {showLabel && <span>Select Agent</span>}
        </Button>
      </ModelSelectorTrigger>

      <ModelSelectorContent shouldFilter={false} className="min-h-[40%]">
        <ModelSelectorInput
          placeholder="Search models..."
          searchValue={modelSearch}
          onSearchChange={setModelSearch}
        />
        <ModelSelectorList>
          {modelsLoading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Loading models...
            </div>
          ) : agentModels.length === 0 ? (
            <ModelSelectorEmpty>No models found.</ModelSelectorEmpty>
          ) : (
            Object.entries(groupedModels).map(([chef, models]) => (
              <ModelSelectorGroup key={chef} heading={chef}>
                {models.map((m) => (
                  <ModelSelectorItem
                    key={m.id}
                    onSelect={() => {
                      onValueChange(m.id);
                      setOpen(false);
                    }}
                    value={m.id}
                  >
                    {m.agent_color ? (
                      <span
                        className="size-4 rounded-full shrink-0 border border-border"
                        style={{ backgroundColor: m.agent_color }}
                        aria-hidden
                      />
                    ) : m.chefSlug ? (
                      <ModelSelectorLogo provider={m.chefSlug} />
                    ) : null}
                    <div className="flex flex-col min-w-0">
                      <ModelSelectorName>{m.name}</ModelSelectorName>
                      {m.model && (
                        <span className="text-xs text-muted-foreground truncate">{m.model}</span>
                      )}
                    </div>
                    <ModelSelectorLogoGroup>
                      {m.providers.map((provider) => (
                        <ModelSelectorLogo key={provider} provider={provider} />
                      ))}
                    </ModelSelectorLogoGroup>
                    {value === m.id ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </ModelSelectorItem>
                ))}
              </ModelSelectorGroup>
            ))
          )}
        </ModelSelectorList>
      </ModelSelectorContent>
    </ModelSelector>
  );
}

