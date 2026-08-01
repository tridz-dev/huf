import { useState, useEffect, useRef, useMemo } from 'react';
import { CheckIcon, ChevronDown, Plus } from 'lucide-react';
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
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getAgentModels, type AgentModelItem } from '@/services/agentApi';
import { ProviderBrandIcon } from '@/components/providers/ProviderBrandIcon';
import { isKnownBrand } from '@/utils/providerBrands';

interface AgentModelSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
  showLabel?: boolean;
  variant?: 'icon' | 'pill';
  currentLabel?: string;
  currentModel?: string | null;
}

export function AgentModelSelector({
  value,
  onValueChange,
  disabled,
  showLabel = false,
  variant = 'icon',
  currentLabel,
  currentModel,
}: AgentModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const isInitialAutoSelectRef = useRef(true);

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
    autoLoadMore: false,
  });

  useEffect(() => {
    if (agentModels.length > 0 && !value && isInitialAutoSelectRef.current) {
      isInitialAutoSelectRef.current = false;
    } else if (agentModels.length > 0 && value) {
      isInitialAutoSelectRef.current = false;
    }
  }, [agentModels, value]);

  useEffect(() => {
    if (open) {
      setModelSearch('');
    }
  }, [open, setModelSearch]);

  const groupedModels = agentModels.reduce(
    (acc, model) => {
      const groupLabel = model.providerBrandLabel || 'Other';
      if (!acc[groupLabel]) {
        acc[groupLabel] = [];
      }
      acc[groupLabel].push(model);
      return acc;
    },
    {} as Record<string, AgentModelItem[]>
  );

  const selectedModel = useMemo(
    () => agentModels.find((m) => m.id === value),
    [agentModels, value]
  );

  const triggerLabel = currentLabel ?? selectedModel?.name ?? 'Select Agent';
  const triggerModel = currentModel ?? selectedModel?.model;

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        {variant === 'pill' ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={disabled}
            className={cn(
              'h-auto gap-1.5 rounded-md border px-2 py-1 text-xs font-normal text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900',
              disabled && 'disabled:opacity-100'
            )}
          >
            <span className="relative flex size-5 shrink-0 items-center justify-center">
              {selectedModel && isKnownBrand(selectedModel.providerBrand) ? (
                <ProviderBrandIcon brand={selectedModel.providerBrand} size="sm" />
              ) : selectedModel?.agent_color ? (
                <span
                  className="size-3.5 rounded-full border border-border"
                  style={{ backgroundColor: selectedModel.agent_color }}
                  aria-hidden
                />
              ) : (
                <span className="size-3.5 shrink-0" aria-hidden />
              )}
            </span>
            <span className="max-w-[12rem] truncate">{triggerLabel}</span>
            {triggerModel ? (
              <span className="text-muted-foreground truncate max-w-[8rem]">· {triggerModel}</span>
            ) : null}
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          </Button>
        ) : (
          <Button
            size={showLabel ? 'default' : 'icon'}
            variant={showLabel ? 'outline' : 'ghost'}
            disabled={disabled}
            className={cn(
              'text-steel hover:bg-paper-deep hover:text-ink',
              showLabel && 'gap-2',
              disabled && 'disabled:opacity-100'
            )}
          >
            <Plus className={showLabel ? 'w-4 h-4' : 'w-5 h-5'} />
            {showLabel && <span>Select Agent</span>}
          </Button>
        )}
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
            Object.entries(groupedModels).map(([groupLabel, models]) => (
              <ModelSelectorGroup key={groupLabel} heading={groupLabel}>
                {models.map((model) => (
                  <ModelSelectorItem
                    key={model.id}
                    className="gap-3 px-3 py-2.5"
                    onSelect={() => {
                      onValueChange(model.id);
                      setOpen(false);
                    }}
                    value={model.id}
                  >
                    <div className="relative flex size-8 shrink-0 items-center justify-center">
                      {isKnownBrand(model.providerBrand) ? (
                        <ProviderBrandIcon brand={model.providerBrand} size="sm" />
                      ) : model.agent_color ? (
                        <span
                          className="size-4 rounded-full border border-border"
                          style={{ backgroundColor: model.agent_color }}
                          aria-hidden
                        />
                      ) : (
                        <span className="size-4 shrink-0" aria-hidden />
                      )}
                      {model.agent_color && isKnownBrand(model.providerBrand) ? (
                        <span
                          className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full border border-background ring-1 ring-border"
                          style={{ backgroundColor: model.agent_color }}
                          aria-hidden
                        />
                      ) : null}
                    </div>

                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <ModelSelectorName>{model.name}</ModelSelectorName>
                      {model.model ? (
                        <span className="text-xs text-muted-foreground truncate">{model.model}</span>
                      ) : null}
                    </div>

                    {value === model.id ? (
                      <CheckIcon className="ml-auto size-4 shrink-0" />
                    ) : (
                      <div className="ml-auto size-4 shrink-0" />
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
