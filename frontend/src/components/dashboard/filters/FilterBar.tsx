import { Fragment, ReactNode, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
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
  collapsibleSearch?: boolean;
}

/** Hairline divider between strip cells. */
const divider = <div className="w-px self-stretch bg-line" />;

/** Select trigger restyled to sit flush inside the strip (no box of its own). */
const flushTriggerClass =
  'h-auto w-auto min-w-[150px] gap-2 rounded-none border-0 bg-transparent px-4 py-0 shadow-none focus:ring-0 focus:ring-offset-0 [&>svg]:text-steel-soft [&>svg]:opacity-100';

function searchInputCell(
  searchPlaceholder: string,
  searchValue: string | undefined,
  onSearchChange: (value: string) => void,
  onSearchSubmit?: () => void,
  autoFocus = false,
  trailing?: ReactNode
) {
  return (
    <div className="flex flex-1 items-center gap-2 px-3.5">
      <Search className="h-4 w-4 shrink-0 text-steel-soft" />
      <input
        placeholder={searchPlaceholder}
        className="w-full bg-transparent py-2.5 font-body text-[13.5px] text-ink outline-none placeholder:text-steel-soft"
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
        <button
          key="search"
          type="button"
          aria-label="Open search"
          className="flex items-center px-3.5 text-steel-soft hover:text-steel"
          onClick={handleToggleSearch}
        >
          <Search className="h-4 w-4" />
        </button>
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
            <button
              type="button"
              aria-label="Close search"
              className="shrink-0 text-steel-soft hover:text-steel"
              onClick={handleToggleSearch}
            >
              <X className="h-4 w-4" />
            </button>
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
          <span className="font-mono text-[11px] uppercase tracking-[.08em] text-steel">
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

  return (
    <div className="flex items-center gap-3">
      {cells.length > 0 && (
        <div className="flex flex-1 items-stretch rounded border border-line bg-panel max-sm:flex-wrap">
          {cells.map((cell, index) => (
            <Fragment key={index}>
              {index > 0 && divider}
              {cell}
            </Fragment>
          ))}
        </div>
      )}
      {actions && (
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
