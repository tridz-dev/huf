import { AskField, CollectionToolbar, FilterPills } from '@/components/patterns';
import type { SourceFilter } from '../import/docFilter';
import type { InputCounts } from '../import/ingestionLabels';

export interface SourceToolbarProps {
  query: string;
  onQueryChange: (v: string) => void;
  onSubmit: () => void;
  filter: SourceFilter;
  onFilterChange: (v: SourceFilter) => void;
  counts: InputCounts;
  hasDocs: boolean;
}

export function SourceToolbar({ query, onQueryChange, onSubmit, filter, onFilterChange, counts, hasDocs }: SourceToolbarProps) {
  const showFilters = hasDocs && !query.trim();
  return (
    <CollectionToolbar
      search={
        <AskField
          value={query}
          onChange={onQueryChange}
          onSubmit={onSubmit}
          placeholder="Ask a question or search these documents…"
        />
      }
      filters={
        showFilters ? (
          <FilterPills<SourceFilter>
            label="Filter by status"
            value={filter}
            onChange={onFilterChange}
            pills={[
              { value: 'all', label: 'All' },
              { value: 'ready', label: 'Ready' },
              { value: 'attention', label: 'Needs attention', count: counts.failed, tone: 'attention', hideEmpty: true },
              { value: 'skipped', label: 'Skipped', count: counts.skipped, hideEmpty: true },
            ]}
          />
        ) : undefined
      }
    />
  );
}
