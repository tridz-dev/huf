import { ChevronDown, Search } from 'lucide-react';
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

const TRIGGER = 'h-control-sm w-auto min-w-[9rem] flex-1 gap-2 rounded-lg border-line bg-panel px-3 py-0 text-ui-text text-ink shadow-none sm:flex-none';

function Dropdown({
  label, value, onChange, options, testId,
}: { label: string; value: string; onChange: (v: string) => void; options: FilterChoice[]; testId: string }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        aria-label={label}
        className={TRIGGER}
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
  return (
    <div className="flex flex-1 flex-wrap items-center gap-2" data-testid="flow-list-filters">
      <InputGroup size="sm" className="min-w-0 basis-full rounded-lg border-line bg-panel shadow-none sm:basis-64 sm:flex-1 sm:max-w-sm">
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
      <Dropdown label="Status" value={props.status} onChange={props.onStatusChange} options={props.statusOptions} testId="flow-list-status-filter" />
      <Dropdown label="Category" value={props.category} onChange={props.onCategoryChange} options={props.categoryOptions} testId="flow-list-category-filter" />
      <Dropdown label="Sort by" value={props.sort} onChange={props.onSortChange} options={props.sortOptions} testId="flow-list-sort" />
    </div>
  );
}
