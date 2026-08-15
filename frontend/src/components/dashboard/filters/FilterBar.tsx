import { Fragment, ReactNode, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select';

interface FilterOption {
  label: string;
  value: string;
}

interface Filter {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}

interface FilterBarProps {
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  onSearchSubmit?: () => void;
  filters?: Filter[];
  actions?: ReactNode;
  primaryAction?: { label: string; icon?: ReactNode; onClick: () => void; disabled?: boolean };
  collapsibleSearch?: boolean;
}

/**
 * Each filter — the search box, each dropdown — is its own distinct 30px
 * / 8px-radius bordered chip, not a shared box divided by internal
 * hairlines. Chips sit side by side with a gap between them.
 */
const CHIP_HEIGHT = 'h-[30px]';
const chipShellClass = `flex ${CHIP_HEIGHT} items-center gap-2 rounded-lg border border-line bg-panel px-3`;

/** Select trigger restyled as its own chip rather than a flush strip cell. */
const flushTriggerClass = `${chipShellClass} w-auto min-w-[140px] gap-2 py-0 shadow-none focus:ring-0 focus:ring-offset-0 [&>svg]:text-steel-soft [&>svg]:opacity-100`;

function searchInputCell(
  searchPlaceholder: string,
  searchValue: string | undefined,
  onSearchChange: (value: string) => void,
  onSearchSubmit?: () => void,
  autoFocus = false,
  trailing?: ReactNode
) {
  return (
    <div className={`${chipShellClass} flex-1`}>
      <Search className="h-3.5 w-3.5 shrink-0 text-steel-soft" />
      <input
        placeholder={searchPlaceholder}
        className="w-full bg-transparent font-body text-[13px] text-ink outline-none placeholder:text-steel-soft"
        value={searchValue}
        onChange={(e) => onSearchChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit();
        }}
        autoFocus={autoFocus}
      />
      {trailing}
    </div>
  );
}

export function FilterBar({
  searchPlaceholder = 'Search...',
  searchValue,
  onSearchChange,
  onSearchSubmit,
  filters = [],
  actions,
  primaryAction,
  collapsibleSearch = false,
}: FilterBarProps) {
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);

  const handleToggleSearch = () => {
    setIsSearchExpanded(!isSearchExpanded);
    if (isSearchExpanded && onSearchChange) {
      onSearchChange('');
    }
  };

  const cells: ReactNode[] = [];

  if (onSearchChange) {
    if (collapsibleSearch && !isSearchExpanded) {
      cells.push(
        <Button
          key="search"
          type="button"
          variant="ghost"
          aria-label="Open search"
          className={`${chipShellClass} justify-center p-0 text-steel-soft hover:bg-panel hover:text-steel`}
          onClick={handleToggleSearch}
        >
          <Search className="h-4 w-4" />
        </Button>
      );
    } else {
      cells.push(
        searchInputCell(
          searchPlaceholder,
          searchValue,
          onSearchChange,
          onSearchSubmit,
          collapsibleSearch,
          collapsibleSearch ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Close search"
              className="h-auto w-auto shrink-0 p-0 text-steel-soft hover:bg-transparent hover:text-steel"
              onClick={handleToggleSearch}
            >
              <X className="h-4 w-4" />
            </Button>
          ) : undefined
        )
      );
    }
  }

  filters.forEach((filter, index) => {
    const isAll = !filter.value || filter.value === 'all';
    const current = isAll
      ? filter.placeholder || 'All'
      : filter.options.find((o) => o.value === filter.value)?.label ?? filter.value;
    cells.push(
      <Select key={`filter-${index}`} value={filter.value} onValueChange={filter.onChange}>
        <SelectTrigger
          className={flushTriggerClass}
          icon={<ChevronDown className="h-3.5 w-3.5 text-steel-soft" />}
        >
          <span className="font-mono text-eyebrow uppercase text-steel">
            {filter.label}: {current}
          </span>
        </SelectTrigger>
        <SelectContent>
          {filter.options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  });

  if (primaryAction) {
    cells.push(
      <Button
        key="primary-action"
        variant="default"
        className={`${CHIP_HEIGHT} gap-2 rounded-lg px-4`}
        onClick={primaryAction.onClick}
        disabled={primaryAction.disabled}
      >
        {primaryAction.icon}
        {primaryAction.label}
      </Button>
    );
  }

  return (
    <div className="flex flex-1 items-stretch gap-3">
      {cells.length > 0 && (
        <div className="flex flex-1 flex-wrap items-center gap-2">
          {cells.map((cell, index) => (
            <Fragment key={index}>{cell}</Fragment>
          ))}
        </div>
      )}
      {actions && (
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
