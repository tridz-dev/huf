import { useEffect, useState } from 'react';
import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { type HufAppManifest } from '@/services/appApi';
import { GridView } from '@/components/dashboard/views/GridView';
import { ItemCard } from '@/components/dashboard/cards/ItemCard';
import { DataRecordList } from '@/components/data-table/DataRecordList';
import { FilterBar } from '@/components/dashboard/filters/FilterBar';
import { useDebounce } from '@/hooks/useDebounce';

interface Props {
  manifest: HufAppManifest;
  tableName: string;
  layoutOverride?: 'grid' | 'list' | 'table';
  filterOverride?: Array<[string, string, string]>;
}

export default function AppCollectionView({ manifest, tableName, layoutOverride, filterOverride }: Props) {
  const viewConfig = manifest.views.find(v => v.table === tableName);
  const layout = layoutOverride ?? viewConfig?.collection_layout ?? 'list';
  const listFields = viewConfig?.list_fields ?? [];

  // Derive the DocType name: HUF tables are named "HF <TableName>"
  const doctypeName = `HF ${tableName}`;

  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const debouncedSearch = useDebounce(search, 300);

  useEffect(() => {
    setLoading(true);
    const filters: Array<[string, string, string]> = [...(filterOverride ?? [])];
    if (debouncedSearch) {
      // Search on first list field if it's a Data type
      const firstField = listFields[0];
      if (firstField) filters.push([firstField, 'like', `%${debouncedSearch}%`]);
    }
    db.getDocList(doctypeName, {
      fields: ['name', ...listFields],
      filters: filters as never,
      limit: 50,
    })
      .then(setRecords)
      .catch(e => handleFrappeError(e, `Failed to load ${tableName}`))
      .finally(() => setLoading(false));
  }, [doctypeName, debouncedSearch, JSON.stringify(filterOverride)]);

  // Field definitions for DataRecordList
  const fieldDefs = listFields.map(f => {
    const fieldDef = manifest.tables
      .find(t => t.table_name === tableName)
      ?.fields.find(fd => fd.fieldname === f);
    return {
      fieldname: f,
      label: fieldDef?.label ?? f,
      fieldtype: (fieldDef?.fieldtype ?? 'Data') as never,
      in_list_view: 1 as const,
    };
  });

  return (
    <div className="flex flex-col gap-4 h-full">
      <FilterBar
        searchPlaceholder={`Search ${tableName}...`}
        searchValue={search}
        onSearchChange={setSearch}
      />
      {layout === 'grid' ? (
        <GridView
          items={records}
          loading={loading}
          keyExtractor={r => String(r.name)}
          columns={{ sm: 1, md: 2, lg: 3 }}
          renderItem={r => (
            <ItemCard
              title={String(r[listFields[0]] ?? r.name ?? '')}
              description={listFields[1] ? String(r[listFields[1]] ?? '') : undefined}
              metadata={listFields.slice(2).map(f => ({
                label: fieldDefs.find(fd => fd.fieldname === f)?.label ?? f,
                value: String(r[f] ?? ''),
              }))}
            />
          )}
        />
      ) : (
        <DataRecordList records={records} fields={fieldDefs} loading={loading} />
      )}
    </div>
  );
}
