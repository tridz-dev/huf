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
  // Use a ref for initialData to avoid effect re-runs when array reference changes
  const initialDataRef = useRef(initialData);
  // Update ref if initialData actually has different content (not just reference)
  const initialDataString = JSON.stringify(initialData);
  const prevInitialDataStringRef = useRef(initialDataString);
  
  if (initialDataString !== prevInitialDataStringRef.current) {
    initialDataRef.current = initialData;
    prevInitialDataStringRef.current = initialDataString;
  }

  const [data, setData] = useState<T[]>(initialDataRef.current);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  // Track fetchFn by reference to detect changes
  const fetchFnRef = useRef(fetchFn);
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    const fetchFnChanged = fetchFnRef.current !== fetchFn;
    fetchFnRef.current = fetchFn;

    // Reset hasFetched if fetchFn changes
    if (fetchFnChanged) {
      hasFetchedRef.current = false;
    }

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
      // Only update data from initialData if we haven't fetched yet
      if (!hasFetchedRef.current) {
        setData(initialDataRef.current);
      }
    }
  }, [fetchFn]); // Only depend on fetchFn, not initialData

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
