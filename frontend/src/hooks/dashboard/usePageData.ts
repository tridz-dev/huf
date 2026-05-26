import { useState, useEffect, useMemo, useCallback, useRef } from 'react';

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
  // State
  const [data, setData] = useState<T[]>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const hasFetched = useRef(false);

  // Fetch data on mount only
  useEffect(() => {
    if (!fetchFn || hasFetched.current) {
      setLoading(false);
      return;
    }

    hasFetched.current = true;
    let cancelled = false;

    const doFetch = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const result = await fetchFn();
        if (!cancelled) {
          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    doFetch();

    return () => {
      cancelled = true;
    };
  }, []); // Empty deps - only run once on mount

  // Filter and search logic
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

  // Manual refresh function
  const refresh = useCallback(async () => {
    if (!fetchFn) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await fetchFn();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [fetchFn]);

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
    refresh,
  };
}
