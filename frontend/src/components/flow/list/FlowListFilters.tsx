import { ChevronDown, Search, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export interface FilterChoice {
  label: string;
  value: string;
}

interface FlowListFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
  statusOptions: FilterChoice[];
  category: string;
  onCategoryChange: (value: string) => void;
  categoryOptions: FilterChoice[];
  sort: string;
  onSortChange: (value: string) => void;
  sortOptions: FilterChoice[];
}

const TRIGGER = 'h-control-sm w-auto min-w-[9rem] gap-2 rounded-lg border-line bg-panel px-3 py-0 text-ui-text text-ink shadow-none';
const TRIGGER_FULL = 'h-control-sm w-full gap-2 rounded-lg border-line bg-panel px-3 py-0 text-ui-text text-ink shadow-none';

function Dropdown({
  label, value, onChange, options, testId, full,
}: { label: string; value: string; onChange: (v: string) => void; options: FilterChoice[]; testId: string; full?: boolean }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        aria-label={label}
        className={full ? TRIGGER_FULL : TRIGGER}
        icon={<ChevronDown className="h-3.5 w-3.5 text-steel-soft" />}
        data-testid={testId}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * Search plus three plain dropdowns: status ("All statuses"), category ("All categories") and sort. Sentence case,
 * no codes. The search looks in the name, the description and the category.
 */
export function FlowListFilters(props: FlowListFiltersProps) {
  // On a phone the three dropdowns fold into one "Filters" button so the row stays one line tall.
  const active = [props.status !== 'all', props.category !== 'all', props.sort !== props.sortOptions[0]?.value].filter(Boolean).length;
  const dropdowns = (full: boolean) => (
    <>
      <Dropdown full={full} label="Status" value={props.status} onChange={props.onStatusChange} options={props.statusOptions} testId={full ? 'flow-list-status-filter-sheet' : 'flow-list-status-filter'} />
      <Dropdown full={full} label="Category" value={props.category} onChange={props.onCategoryChange} options={props.categoryOptions} testId={full ? 'flow-list-category-filter-sheet' : 'flow-list-category-filter'} />
      <Dropdown full={full} label="Sort by" value={props.sort} onChange={props.onSortChange} options={props.sortOptions} testId={full ? 'flow-list-sort-sheet' : 'flow-list-sort'} />
    </>
  );
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2" data-testid="flow-list-filters">
      <InputGroup size="sm" className="min-w-0 flex-1 rounded-lg border-line bg-panel shadow-none sm:max-w-sm">
        <InputGroupAddon align="inline-start" className="py-0">
          <Search className="h-3.5 w-3.5 shrink-0 text-steel-soft" />
        </InputGroupAddon>
        <InputGroupInput
          aria-label="Search flows by name, description or category"
          title="Looks in names, descriptions and categories"
          placeholder="Search flows..."
          className="text-ui-text text-ink placeholder:text-steel-soft"
          value={props.search}
          onChange={(e) => props.onSearchChange(e.target.value)}
          data-testid="flow-list-search"
        />
      </InputGroup>
      <div className="hidden items-center gap-2 sm:flex">{dropdowns(false)}</div>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="shrink-0 gap-1.5 sm:hidden" data-testid="flow-list-filters-button" aria-label={active ? `Filters (${active} on)` : 'Filters'}>
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden />
            Filters{active ? ` (${active})` : ''}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="grid w-64 gap-2 p-3" data-testid="flow-list-filters-sheet">
          {dropdowns(true)}
        </PopoverContent>
      </Popover>
    </div>
  );
}
