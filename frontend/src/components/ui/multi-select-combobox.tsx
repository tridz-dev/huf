import * as React from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

export interface MultiSelectComboboxOption {
  value: string;
  label: string;
  description?: string;
}

interface MultiSelectComboboxProps {
  options: MultiSelectComboboxOption[];
  values?: string[];
  onValuesChange?: (values: string[]) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  className?: string;
  maxBadges?: number;
}

export function MultiSelectCombobox({
  options,
  values = [],
  onValuesChange,
  placeholder = 'Select options...',
  searchPlaceholder = 'Search...',
  emptyText = 'No results found.',
  disabled = false,
  className,
  maxBadges = 3,
}: MultiSelectComboboxProps) {
  const [open, setOpen] = React.useState(false);

  const selectedOptions = React.useMemo(
    () => options.filter((option) => values.includes(option.value)),
    [options, values]
  );

  const toggleValue = (value: string) => {
    const nextValues = values.includes(value)
      ? values.filter((currentValue) => currentValue !== value)
      : [...values, value];

    onValuesChange?.(nextValues);
  };

  const removeValue = (value: string) => {
    onValuesChange?.(values.filter((currentValue) => currentValue !== value));
  };

  const visibleBadges = selectedOptions.slice(0, maxBadges);
  const hiddenCount = selectedOptions.length - visibleBadges.length;

  return (
    <div className={cn('space-y-2', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
            disabled={disabled}
          >
            <span className="truncate text-left text-sm text-muted-foreground">
              {selectedOptions.length > 0
                ? `${selectedOptions.length} selected`
                : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              <CommandGroup>
                {options.map((option) => {
                  const isSelected = values.includes(option.value);

                  return (
                    <CommandItem
                      key={option.value}
                      value={`${option.label} ${option.description || ''}`}
                      onSelect={() => toggleValue(option.value)}
                      className="flex items-start gap-2"
                    >
                      <Check
                        className={cn(
                          'mt-0.5 h-4 w-4 shrink-0',
                          isSelected ? 'opacity-100' : 'opacity-0'
                        )}
                      />
                      <div className="min-w-0">
                        <div className="truncate">{option.label}</div>
                        {option.description ? (
                          <div className="text-xs text-muted-foreground">{option.description}</div>
                        ) : null}
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {selectedOptions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {visibleBadges.map((option) => (
            <Badge key={option.value} variant="secondary" className="gap-1 pr-1">
              <span className="max-w-[180px] truncate">{option.label}</span>
              <button
                type="button"
                className="rounded-sm p-0.5 hover:bg-background/70"
                onClick={() => removeValue(option.value)}
                aria-label={`Remove ${option.label}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {hiddenCount > 0 ? <Badge variant="outline">+{hiddenCount} more</Badge> : null}
        </div>
      ) : null}
    </div>
  );
}
