  import * as React from 'react';
  import { ChevronsUpDown} from 'lucide-react';

  import {
    Combobox,
    ComboboxChip,
    ComboboxChips,
    ComboboxChipsInput,
    ComboboxContent,
    ComboboxEmpty,
    ComboboxItem,
    ComboboxList,
    ComboboxValue,
    useComboboxAnchor,
  } from '@/components/ui/combobox';
  import { Button } from '@/components/ui/button';
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
    closeLabel?: string;
    disabled?: boolean;
    className?: string;
    maxBadges?: number;
    searchValue?: string;
    onSearchChange?: (value: string) => void;
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
    searchValue,
    onSearchChange,
  }: MultiSelectComboboxProps) {
    const anchor = useComboboxAnchor();
    const [open, setOpen] = React.useState(false);
    const optionByValue = new Map(options.map((option) => [option.value, option]));
    const selectedOptions = options.filter((option) => values.includes(option.value));
    const visibleOptions = selectedOptions.slice(0, maxBadges);
    const hiddenCount = selectedOptions.length - visibleOptions.length;

    return (
      <div className={cn('space-y-2', className)}>
        <Combobox
          multiple
          autoHighlight
          items={options.map((option) => option.value)}
          value={values}
          onValueChange={(nextValues) => onValuesChange?.(nextValues as string[])}
          itemToStringLabel={(value: string) => optionByValue.get(value)?.label || value}
          itemToStringValue={(value: string) => value}
          filter={(value: string, query: string) => {
            const option = optionByValue.get(value);
            return `${option?.label || ''} ${option?.description || ''}`
              .toLocaleLowerCase()
              .includes(query.toLocaleLowerCase());
          }}
          inputValue={onSearchChange ? searchValue : undefined}
          onInputValueChange={(nextSearch, eventDetails) => {
            if (eventDetails.isItemPress) {
              eventDetails.cancel();
              return;
            }
            onSearchChange?.(nextSearch);
          }}
          open={open}
          onOpenChange={(nextOpen, eventDetails) => {
            if (!nextOpen && eventDetails.reason === 'item-press') {
              eventDetails.cancel();
              return;
            }
            setOpen(nextOpen);
          }}
          disabled={disabled}
        >
          <ComboboxChips ref={anchor} className="gap-1.5">
            <ComboboxValue>
              {(selectedValues: string[]) => (
                <>
                  {visibleOptions.map((option) => (
                    <ComboboxChip
                      key={option.value}
                      removeLabel={`Remove ${option.label}`}
                      className="gap-1 pr-1"
                    >
                      <span className="max-w-[180px] truncate">{option.label}</span>
                    </ComboboxChip>
                  ))}
                  {hiddenCount > 0 ? (
                    <span className="rounded-sm border px-1.5 py-0.5 text-xs text-muted-foreground">
                      +{hiddenCount} more
                    </span>
                  ) : null}
                  <ComboboxChipsInput
                    placeholder={selectedValues.length === 0 ? placeholder : searchPlaceholder}
                    disabled={disabled}
                    aria-label={searchPlaceholder}
                  />
                  <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <ComboboxContent
            anchor={anchor}
            portalContainer={anchor.current?.closest<HTMLElement>('[role="dialog"]')}
          className="flex max-h-[min(20rem,var(--available-height))] w-[var(--anchor-width)] flex-col p-0"
          >
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="text-xs font-medium text-muted-foreground">Select options</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => setOpen(false)}
              >
              Done
              </Button>
            </div>
              <ComboboxEmpty>{emptyText}</ComboboxEmpty>
              <ComboboxList  className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
                {(value: string) => {
                  const option = optionByValue.get(value);
                  if (!option) return null;

                  return (
                    <ComboboxItem key={option.value} value={option.value} className="items-start">
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate">{option.label}</span>
                        {option.description ? (
                          <span className="truncate text-xs text-muted-foreground">
                            {option.description}
                          </span>
                        ) : null}
                      </span>
                    </ComboboxItem>
                  );
                }}
              </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </div>
    );
  }