"use client";

import { useState, useEffect } from 'react';
import { CheckIcon } from 'lucide-react';
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
import { PromptInputButton } from '@/components/ai-elements/prompt-input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getAgentModels, type AgentModelItem } from '@/services/agentApi';

interface AgentModelSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  onModelNameChange?: (name: string) => void;
  disabled?: boolean;
  variant?: 'default' | 'header';
}

export function AgentModelSelector({ value, onValueChange, onModelNameChange, disabled, variant = 'default' }: AgentModelSelectorProps) {
  const [open, setOpen] = useState(false);

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

  // Set default model when models load
  useEffect(() => {
    if (agentModels.length > 0 && !value) {
      onValueChange(agentModels[0].id);
    }
  }, [agentModels, value, onValueChange]);

  // Reset search when modal opens
  useEffect(() => {
    if (open) {
      setModelSearch('');
    }
  }, [open, setModelSearch]);

  const selectedModelData = agentModels.find((m) => m.id === value);

  // Notify parent of model name change
  useEffect(() => {
    if (onModelNameChange) {
      if (selectedModelData) {
        onModelNameChange(selectedModelData.name);
      } else if (modelsLoading) {
        onModelNameChange('Loading...');
      } else {
        onModelNameChange('');
      }
    }
  }, [selectedModelData, onModelNameChange, modelsLoading]);

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

  const TriggerButton = variant === 'header' ? Button : PromptInputButton;

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        <TriggerButton 
          disabled={disabled}
          variant={variant === 'header' ? 'ghost' : undefined}
          className={cn(
            variant === 'header' && 'h-auto p-0 gap-x-1 items-center text-sm font-semibold hover:bg-transparent',
            variant === 'header' && disabled && 'disabled:opacity-100'
          )}
        >
          {selectedModelData?.chefSlug && (
            <ModelSelectorLogo provider={selectedModelData.chefSlug} />
          )}
          {selectedModelData?.name ? (
            <ModelSelectorName>{selectedModelData.name}</ModelSelectorName>
          ) : (
            variant === 'header' && (
              <span className={cn(disabled && 'text-muted-foreground')}>
                {modelsLoading ? 'Loading...' : 'No model selected'}
              </span>
            )
          )}
        </TriggerButton>
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
                    {m.chefSlug && <ModelSelectorLogo provider={m.chefSlug} />}
                    <ModelSelectorName>{m.name}</ModelSelectorName>
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

