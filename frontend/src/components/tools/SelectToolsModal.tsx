import { useState, useEffect, useMemo } from 'react';
import { Search, Check, ChevronsUpDown } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '../ui/command';
import { ToolCard } from './ToolCard';
import { getToolFunctions, getToolTypes } from '@/services/toolApi';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface SelectToolsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedTools: AgentToolFunctionRef[];
  onAddTools: (tools: AgentToolFunctionRef[]) => void;
}

export function SelectToolsModal({
  open,
  onOpenChange,
  selectedTools,
  onAddTools,
}: SelectToolsModalProps) {
  const [allTools, setAllTools] = useState<AgentToolFunctionRef[]>([]);
  const [toolTypes, setToolTypes] = useState<AgentToolType[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [toolTypeFilter, setToolTypeFilter] = useState<string>('all');
  const [comboboxOpen, setComboboxOpen] = useState(false);
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(
    new Set(selectedTools.map((t) => t.name))
  );

  // Load tools and tool types when modal opens
  useEffect(() => {
    if (open) {
      setLoading(true);
      Promise.all([
        getToolTypes(),
        getToolFunctions(),
      ])
        .then(([types, tools]) => {
          setToolTypes(types);
          setAllTools(tools);
          setLoading(false);
        })
        .catch((error) => {
          console.error('Error loading tools/types:', error);
          toast.error('Failed to load tools');
          setLoading(false);
        });
      
      // Reset filters and selection when opening
      setSearchQuery('');
      setToolTypeFilter('all');
      setComboboxOpen(false);
      setSelectedToolIds(new Set(selectedTools.map((t) => t.name)));
    }
  }, [open, selectedTools]);

  // Update selected tool IDs when selectedTools prop changes
  useEffect(() => {
    if (open) {
      setSelectedToolIds(new Set(selectedTools.map((t) => t.name)));
    }
  }, [selectedTools, open]);

  // Create a map of tool_type name -> AgentToolType for quick lookup
  const toolTypesMap = useMemo(() => {
    const map = new Map<string, AgentToolType>();
    toolTypes.forEach((type) => {
      map.set(type.name, type);
    });
    return map;
  }, [toolTypes]);

  // Filter tools based on search and tool_type filter
  const filteredTools = useMemo(() => {
    return allTools.filter((tool) => {
      // Search filter - search by name (which is the tool_name) and description
      const matchesSearch =
        searchQuery === '' ||
        (tool.tool_name || tool.name).toLowerCase().includes(searchQuery.toLowerCase()) ||
        tool.description?.toLowerCase().includes(searchQuery.toLowerCase());

      // Tool type filter (using tool_type link field)
      const matchesToolType = toolTypeFilter === 'all' || tool.tool_type === toolTypeFilter;

      return matchesSearch && matchesToolType;
    });
  }, [allTools, searchQuery, toolTypeFilter]);

  const handleToolToggle = (tool: AgentToolFunctionRef) => {
    const newSelectedIds = new Set(selectedToolIds);
    if (newSelectedIds.has(tool.name)) {
      newSelectedIds.delete(tool.name);
    } else {
      newSelectedIds.add(tool.name);
    }
    setSelectedToolIds(newSelectedIds);
  };

  const handleAdd = () => {
    const toolsToAdd = filteredTools.filter((tool) =>
      selectedToolIds.has(tool.name)
    );
    
    // Only add tools that aren't already selected
    const newTools = toolsToAdd.filter(
      (tool) => !selectedTools.some((st) => st.name === tool.name)
    );

    if (newTools.length === 0) {
      toast.info('No new tools selected');
      return;
    }

    onAddTools(newTools);
    toast.success(`Added ${newTools.length} tool${newTools.length > 1 ? 's' : ''}`);
    onOpenChange(false);
  };

  const selectedCount = filteredTools.filter((tool) =>
    selectedToolIds.has(tool.name)
  ).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] h-[80vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle>Select Tools</DialogTitle>
          <DialogDescription>
            Choose tools to add to this agent. Select multiple tools at once.
          </DialogDescription>
        </DialogHeader>

        {/* Filters */}
        <div className="flex flex-col gap-3 px-6 pb-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search tools by name or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Tool Type Filter - Combobox */}
          <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                role="combobox"
                aria-expanded={comboboxOpen}
                className="w-full justify-between"
              >
                {toolTypeFilter === 'all'
                  ? 'All Tool Types'
                  : toolTypes.find((type) => type.name === toolTypeFilter)?.name1 || 'Select tool type...'}
                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
              <Command>
                <CommandInput placeholder="Search tool types..." className="h-9" />
                <CommandList>
                  <CommandEmpty>No tool type found.</CommandEmpty>
                  <CommandGroup>
                    <CommandItem
                      value="all"
                      onSelect={() => {
                        setToolTypeFilter('all');
                        setComboboxOpen(false);
                      }}
                    >
                      <Check
                        className={cn(
                          'mr-2 h-4 w-4',
                          toolTypeFilter === 'all' ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                      All Tool Types
                    </CommandItem>
                    {toolTypes.map((type) => (
                      <CommandItem
                        key={type.name}
                        value={type.name1}
                        onSelect={() => {
                          setToolTypeFilter(type.name === toolTypeFilter ? 'all' : type.name);
                          setComboboxOpen(false);
                        }}
                      >
                        <Check
                          className={cn(
                            'mr-2 h-4 w-4',
                            toolTypeFilter === type.name ? 'opacity-100' : 'opacity-0'
                          )}
                        />
                        {type.name1}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>

        {/* Tool List */}
        <div className="flex-1 overflow-y-auto min-h-0 px-6 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-muted-foreground">Loading tools...</div>
            </div>
          ) : filteredTools.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-muted-foreground">
                {searchQuery || toolTypeFilter !== 'all'
                  ? 'No tools match your filters'
                  : 'No tools available'}
              </div>
            </div>
          ) : (
            filteredTools.map((tool) => (
              <ToolCard
                key={tool.name}
                tool={tool}
                selected={selectedToolIds.has(tool.name)}
                onSelect={handleToolToggle}
                compact
                toolTypesMap={toolTypesMap}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="flex items-center justify-between border-t px-6 py-4">
          <div className="text-sm text-muted-foreground">
            {selectedCount > 0 ? (
              <>
                {selectedCount} tool{selectedCount > 1 ? 's' : ''} selected
                {selectedCount !== filteredTools.length && (
                  <> • {filteredTools.length} total</>
                )}
              </>
            ) : (
              <>{filteredTools.length} tool{filteredTools.length !== 1 ? 's' : ''} available</>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={selectedCount === 0}>
              Add {selectedCount > 0 && `(${selectedCount})`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

