import { useState, useEffect, useCallback, useRef } from 'react';
import { useDebounce } from './useDebounce';
import { PaginationParams, PaginatedResponse } from '@/types/pagination';

export interface UseInfiniteScrollOptions<TParams extends PaginationParams, TItem> {
  /**
   * Function to fetch data from the API
   * Should accept pagination parameters and return a promise with paginated data
   */
  fetchFn: (params: TParams) => Promise<PaginatedResponse<TItem>>;

  /**
   * Initial parameters to pass to fetchFn (excluding pagination params)
   */
  initialParams?: Omit<TParams, 'page' | 'limit' | 'start'>;

  /**
   * Number of items to fetch per page
   * @default 20
   */
  pageSize?: number;

  /**
   * Debounce delay for search and filters in milliseconds
   * @default 300
   */
  debounceMs?: number;

  /**
   * Whether to automatically load first page on mount
   * @default true
   */
  autoLoad?: boolean;

  /**
   * Whether to automatically observe the sentinel element and load more items
   * @default true
   */
  autoLoadMore?: boolean;

  /**
   * Root margin to use for the intersection observer when auto loading more items
   * @default '0px 0px 200px 0px'
   */
  rootMargin?: string;

}

export interface UseInfiniteScrollReturn<TItem> {
  /**
   * All loaded items accumulated across pages
   */
  items: TItem[];

  /**
   * Whether more data is available to load
   */
  hasMore: boolean;

  /**
   * Whether data is currently being fetched
   */
  loading: boolean;

  /**
   * Whether the initial load is in progress
   */
  initialLoading: boolean;

  /**
   * Whether more data is being loaded
   */
  loadingMore: boolean;

  /**
   * Error object if fetch failed
   */
  error: Error | null;

  /**
   * Current search query
   */
  search: string;

  /**
   * Set search query (debounced)
   */
  setSearch: (search: string) => void;

  /**
   * Current filters
   */
  filters: Record<string, string>;

  /**
   * Set a filter value
   */
  setFilter: (key: string, value: string) => void;

  /**
   * Set multiple filters at once
   */
  setFilters: (filters: Record<string, string>) => void;

  /**
   * Manually load more data
   */
  loadMore: () => Promise<void>;

  /**
   * Reset pagination and reload from first page
   */
  reset: () => Promise<void>;

  /**
   * Total number of items (if provided by API)
   */
  total: number | undefined;

  /**
   * Ref for the scroll container. Attach to a scrollable element to scope the observer.
   */
  scrollRef: React.MutableRefObject<HTMLDivElement | null>;

  /**
   * Ref for the sentinel element. Place at the end of the list to trigger loading more items.
   */
  sentinelRef: React.MutableRefObject<HTMLDivElement | null>;
}

/**
 * Reusable hook for infinite scrolling with pagination, search, and filters
 * Uses Intersection Observer API for efficient scroll detection
 *
 * @example
 * ```tsx
 * const {
 *   items,
 *   hasMore,
 *   loading,
 *   search,
 *   setSearch,
 *   filters,
 *   setFilter,
 *   scrollRef,
 *   sentinelRef,
 * } = useInfiniteScroll({
 *   fetchFn: async (params) => {
 *     const response = await getAgents({
 *       page: params.page,
 *       limit: params.limit,
 *       search: params.search,
 *     });
 *     return {
 *       data: response.items,
 *       hasMore: response.hasMore,
 *       total: response.total,
 *     };
 *   },
 *   initialParams: {},
 *   pageSize: 20,
 * });
 *
 * return (
 *   <div ref={scrollRef} className="overflow-auto">
 *     {items.map(item => <Item key={item.id} {...item} />)}
 *     Sentinel element at the bottom:
 *     {hasMore && <div ref={sentinelRef} className="h-4" />}
 *     {loadingMore && <LoadingSpinner />}
 *   </div>
 * );
 * ```
 */
export function useInfiniteScroll<TParams extends PaginationParams, TItem>({
  fetchFn,
  initialParams = {} as Omit<TParams, 'page' | 'limit' | 'start'>,
  pageSize = 20,
  debounceMs = 300,
  autoLoad = true,
  autoLoadMore = true,
  rootMargin = '0px 0px 200px 0px',
}: UseInfiniteScrollOptions<TParams, TItem>): UseInfiniteScrollReturn<TItem> {
  const [items, setItems] = useState<TItem[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(autoLoad);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [search, setSearchRaw] = useState('');
  const [filters, setFiltersRaw] = useState<Record<string, string>>({});
  const [total, setTotal] = useState<number | undefined>(undefined);

  const currentPageRef = useRef(0);
  const isFetchingRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Debounce search and filters
  const debouncedSearch = useDebounce(search, debounceMs);
  const debouncedFilters = useDebounce(filters, debounceMs);

  // Note: fetchParams removed - we build params directly in fetchData
  // to ensure we always use the current page ref value

  // Fetch data function
  const fetchData = useCallback(
    async (append = false) => {
      if (isFetchingRef.current) return;

      try {
        isFetchingRef.current = true;

        if (append) {
          setLoadingMore(true);
        } else {
          setLoading(true);
          setInitialLoading(true);
        }

        setError(null);

        // Build params with current page ref for accurate pagination
        const start = currentPageRef.current * pageSize;
        const params: TParams = {
          ...initialParams,
          page: currentPageRef.current + 1,
          limit: pageSize,
          start,
          search: debouncedSearch || undefined,
          ...debouncedFilters,
        } as TParams;

        const response = await fetchFn(params);

        if (append) {
          setItems((prev) => [...prev, ...response.data]);
        } else {
          setItems(response.data);
          currentPageRef.current = 0;
        }

        setHasMore(response.hasMore);
        // Only update total if it's provided (from first page)
        if (response.total !== undefined) {
          setTotal(response.total);
        }

        if (response.hasMore) {
          currentPageRef.current += 1;
        }
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Failed to fetch data');
        setError(error);
        setItems([]);
        setHasMore(false);
        setTotal(undefined); // Reset total on error
      } finally {
        setLoading(false);
        setInitialLoading(false);
        setLoadingMore(false);
        isFetchingRef.current = false;
      }
    },
    [fetchFn, initialParams, pageSize, debouncedSearch, debouncedFilters]
  );

  // Reset and reload from first page
  const reset = useCallback(async () => {
    currentPageRef.current = 0;
    setHasMore(true);
    await fetchData(false);
  }, [fetchData]);

  // Load more data
  const loadMore = useCallback(async () => {
    if (!hasMore || loading || loadingMore || isFetchingRef.current) return;
    await fetchData(true);
  }, [hasMore, loading, loadingMore, fetchData]);

  // Automatically observe sentinel element to load more items
  useEffect(() => {
    if (!autoLoadMore || !hasMore) {
      return;
    }

    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry?.isIntersecting) {
          loadMore();
        }
      },
      {
        root: scrollRef.current ?? null,
        rootMargin,
      }
    );

    observer.observe(sentinel);

    return () => {
      observer.disconnect();
    };
  }, [autoLoadMore, hasMore, loadMore, rootMargin, items.length]);

  // Set search query
  const setSearch = useCallback((value: string) => {
    setSearchRaw(value);
    currentPageRef.current = 0;
    setHasMore(true);
  }, []);

  // Set a single filter
  const setFilter = useCallback((key: string, value: string) => {
    setFiltersRaw((prev) => {
      const newFilters = { ...prev };
      if (value === '' || value === 'all') {
        delete newFilters[key];
      } else {
        newFilters[key] = value;
      }
      return newFilters;
    });
    currentPageRef.current = 0;
    setHasMore(true);
  }, []);

  // Set multiple filters
  const setFilters = useCallback((newFilters: Record<string, string>) => {
    setFiltersRaw(newFilters);
    currentPageRef.current = 0;
    setHasMore(true);
  }, []);

  // Auto-load on mount
  useEffect(() => {
    if (autoLoad) {
      fetchData(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reset and reload when search or filters change (debounced)
  useEffect(() => {
    if (autoLoad) {
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, debouncedFilters]);

  return {
    items,
    hasMore,
    loading,
    initialLoading,
    loadingMore,
    error,
    search,
    setSearch,
    filters,
    setFilter,
    setFilters,
    loadMore,
    reset,
    total,
    scrollRef,
    sentinelRef,
  };
}