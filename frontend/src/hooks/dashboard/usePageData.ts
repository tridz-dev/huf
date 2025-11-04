import { useState, useEffect, useMemo, useRef } from 'react';

interface UsePageDataOptions<T> {
  fetchFn?: () => Promise<T[]>;
  initialData?: T[];
  searchFields?: (keyof T)[];
  filterFn?: (item: T, filters: Record<string, string>) => boolean;
}

export function usePageData<T>({
  fetchFn,
  initialData = [],
  searchFields = [],
  filterFn,
}: UsePageDataOptions<T>) {
  const [data, setData] = useState<T[]>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (fetchFn && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      setLoading(true);
      fetchFn()
        .then((result) => {
          setData(result);
          setError(null);
        })
        .catch((err) => {
          setError(err);
        })
        .finally(() => {
          setLoading(false);
        });
    } else if (!fetchFn) {
      setData(initialData);
    }
  }, [fetchFn, initialData]);

  const filteredData = useMemo(() => {
    let result = [...data];

    if (search && searchFields.length > 0) {
      const searchLower = search.toLowerCase();
      result = result.filter((item) =>
        searchFields.some((field) => {
          const value = item[field];
          if (typeof value === 'string') {
            return value.toLowerCase().includes(searchLower);
          }
          return false;
        })
      );
    }

    if (filterFn && Object.keys(filters).length > 0) {
      result = result.filter((item) => filterFn(item, filters));
    }

    return result;
  }, [data, search, searchFields, filters, filterFn]);

  return {
    data: filteredData,
    allData: data,
    loading,
    error,
    search,
    setSearch,
    filters,
    setFilters,
    setData,
  };
}
