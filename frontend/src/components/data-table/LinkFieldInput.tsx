import { useEffect, useState, useMemo } from 'react';
import { Combobox, ComboboxOption } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { getTableRecords, getTableRecord } from '@/services/dataTableApi';
import { db } from '@/lib/frappe-sdk';

export interface LinkFieldInputProps {
  targetDoctype?: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function LinkFieldInput({ targetDoctype, value, onChange, disabled }: LinkFieldInputProps) {
  const [options, setOptions] = useState<ComboboxOption[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [titleField, setTitleField] = useState<string>('name');
  
  // Single selected record info to show label if not in current options list
  const [selectedRecordLabel, setSelectedRecordLabel] = useState<string | null>(null);

  // Fetch title_field from schema
  useEffect(() => {
    if (!targetDoctype) return;
    
    let isMounted = true;
    const init = async () => {
      try {
        const result = await db.getDocList('Huf Data Table', {
          fields: ['name', 'title_field_name'],
          filters: [['doctype_name', '=', targetDoctype]],
          limit: 1
        });
        if (isMounted && result && result.length > 0 && result[0].title_field_name) {
          setTitleField(result[0].title_field_name);
        }
      } catch (err) {
        console.error('Failed to fetch schema for link field', err);
      }
    };
    init();
    
    return () => { isMounted = false; };
  }, [targetDoctype]);

  // Fetch current selected record to show correct label initially
  useEffect(() => {
    if (!targetDoctype || !value) {
      setSelectedRecordLabel(null);
      return;
    }
    
    let isMounted = true;
    const fetchSelected = async () => {
      try {
        const record = await getTableRecord(targetDoctype, value);
        if (isMounted && record) {
          const label = String(record[titleField] || record.name || value);
          setSelectedRecordLabel(label);
        }
      } catch {
        // If not found, just fallback
        if (isMounted) setSelectedRecordLabel(value);
      }
    };
    
    // We only need to fetch if the selected value isn't already in our options list
    if (!options.some(opt => opt.value === value)) {
      fetchSelected();
    } else {
      const opt = options.find(o => o.value === value);
      setSelectedRecordLabel(opt?.label || value);
    }
    
    return () => { isMounted = false; };
  }, [targetDoctype, value, titleField, options]);

  // Debounced search
  useEffect(() => {
    if (!targetDoctype) return;

    let isMounted = true;
    const timeout = setTimeout(async () => {
      setLoading(true);
      try {
        const filters: Array<[string, string, unknown]> = [];
        if (search.trim()) {
          // Typically we search by title_field or name. Let's use name if title_field is name.
          filters.push([titleField, 'like', `%${search}%`]);
        }
        
        // We only need name and the title field
        const fields = titleField === 'name' ? ['name'] : ['name', titleField];
        
        const result = await getTableRecords(targetDoctype, {
          filters: filters.length > 0 ? filters : undefined,
          limit: 20,
          fields
        });
        
        if (isMounted && result) {
          const newOptions = result.items.map(item => ({
            value: String(item.name),
            label: String(item[titleField] || item.name)
          }));
          setOptions(newOptions);
        }
      } catch (err) {
        console.error('Failed to search link field', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }, 300);

    return () => {
      isMounted = false;
      clearTimeout(timeout);
    };
  }, [targetDoctype, search, titleField]);

  // Ensure current value is included in options so Combobox can display it
  const allOptions = useMemo(() => {
    const list = [...options];
    if (value && !list.some(opt => opt.value === value)) {
      list.push({
        value,
        label: selectedRecordLabel || value
      });
    }
    return list;
  }, [options, value, selectedRecordLabel]);

  if (!targetDoctype) {
    return (
      <Input
        type="text"
        value={value || ''}
        disabled
        placeholder="No target table selected"
        className="h-8 text-sm bg-panel border-line text-steel rounded-none"
      />
    );
  }

  return (
    <Combobox
      options={allOptions}
      value={value}
      onValueChange={onChange}
      disabled={disabled || (loading && options.length === 0)}
      placeholder={loading && options.length === 0 ? 'Loading...' : `Select ${targetDoctype}...`}
      searchPlaceholder="Search..."
      emptyText={loading ? 'Searching...' : 'No record found.'}
      onSearchChange={setSearch}
      shouldFilter={false}
    />
  );
}
