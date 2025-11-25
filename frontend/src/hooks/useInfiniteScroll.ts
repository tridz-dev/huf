import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
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

  /**
   * Scroll direction. Use 'reverse' to prepend earlier pages (e.g., chat history).
   * @default 'forward'
   */
  direction?: 'forward' | 'reverse';

  /**
   * Strategy to merge new pages into the existing list.
   * Defaults to 'prepend' when direction is 'reverse'.
   */
  mergeStrategy?: 'append' | 'prepend';

  /**
   * Preserve scroll position when prepending data (useful for reverse chat views).
   * Defaults to true when direction is 'reverse'.
   */
  preserveScrollPosition?: boolean;

  /**
   * Whether the hook should actively load data.
   * @default true
   */
  enabled?: boolean;
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
  rootMargin,
  direction = 'forward',
  mergeStrategy,
  preserveScrollPosition,
  enabled = true,
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
  const fetchFnRef = useRef(fetchFn);
  const initialParamsRef = useRef(initialParams);
  const initialParamsKey = useMemo(() => JSON.stringify(initialParams), [initialParams]);

  const isReverse = direction === 'reverse';
  const effectiveMergeStrategy = mergeStrategy ?? (isReverse ? 'prepend' : 'append');
  const effectiveRootMargin =
    rootMargin ?? (isReverse ? '200px 0px 0px 0px' : '0px 0px 200px 0px');
  const shouldPreserveScroll =
    preserveScrollPosition ?? (isReverse && effectiveMergeStrategy === 'prepend');
  const isEnabled = enabled;

  useEffect(() => {
    fetchFnRef.current = fetchFn;
  }, [fetchFn]);

  useEffect(() => {
    initialParamsRef.current = initialParams;
  }, [initialParams]);

  // Debounce search and filters
  const debouncedSearch = useDebounce(search, debounceMs);
  const debouncedFilters = useDebounce(filters, debounceMs);

  // Fetch data function
  const fetchData = useCallback(
    async (append = false) => {
      if (!isEnabled || isFetchingRef.current) return;

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
          ...initialParamsRef.current,
          page: currentPageRef.current + 1,
          limit: pageSize,
          start,
          search: debouncedSearch || undefined,
          ...debouncedFilters,
        } as TParams;

        const shouldCaptureScroll = append && shouldPreserveScroll;
        let prevScrollHeight: number | null = null;
        let prevScrollTop: number | null = null;

        if (shouldCaptureScroll) {
          const scrollElement = scrollRef.current;
          if (scrollElement) {
            prevScrollHeight = scrollElement.scrollHeight;
            prevScrollTop = scrollElement.scrollTop;
          }
        }

        const response = await fetchFnRef.current(params);

        if (append) {
          setItems((prev) =>
            effectiveMergeStrategy === 'prepend'
              ? [...response.data, ...prev]
              : [...prev, ...response.data]
          );
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

        const previousHeight = prevScrollHeight;
        const previousTop = prevScrollTop;

        if (
          shouldCaptureScroll &&
          previousHeight !== null &&
          previousTop !== null
        ) {
          requestAnimationFrame(() => {
            const element = scrollRef.current;
            if (!element) return;
            const newHeight = element.scrollHeight;
            element.scrollTop = newHeight - previousHeight + previousTop;
          });
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
    [
      pageSize,
      debouncedSearch,
      debouncedFilters,
      isEnabled,
      effectiveMergeStrategy,
      shouldPreserveScroll,
    ]
  );

  // Reset and reload from first page
  const reset = useCallback(async () => {
    currentPageRef.current = 0;
    setHasMore(true);
    await fetchData(false);
  }, [fetchData]);

  // Load more data
  const loadMore = useCallback(async () => {
    if (!isEnabled || !hasMore || loading || loadingMore || isFetchingRef.current) return;
    await fetchData(true);
  }, [isEnabled, hasMore, loading, loadingMore, fetchData]);

  // Track if we should ignore the first intersection (when sentinel is initially visible)
  const ignoreFirstIntersectionRef = useRef(true);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Reset ignore flag when initial load completes (backup in case observer never triggers)
  useEffect(() => {
    if (!initialLoading) {
      ignoreFirstIntersectionRef.current = false;
    }
  }, [initialLoading]);

  // Automatically observe sentinel element to load more items
  useEffect(() => {
    if (!autoLoadMore || !hasMore || !isEnabled) {
      return;
    }

    // Use requestAnimationFrame to ensure DOM has settled after items change
    const rafId = requestAnimationFrame(() => {
      const sentinel = sentinelRef.current;
      if (!sentinel) {
        return;
      }

      // Disconnect previous observer if it exists
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }

      // Find the scrollable parent if scrollRef is not set or not scrollable
      let scrollElement = scrollRef.current;
      
      // Verify that scrollRef.current is actually scrollable
      if (scrollElement) {
        const style = window.getComputedStyle(scrollElement);
        const isScrollable =
          style.overflowY === 'auto' ||
          style.overflowY === 'scroll' ||
          style.overflow === 'auto' ||
          style.overflow === 'scroll';
        
        if (!isScrollable) {
          scrollElement = null; // Reset to null so fallback logic runs
        }
      }
      
      // Find the scrollable parent if scrollRef is not set or not scrollable
      if (!scrollElement) {
        let parent = sentinel.parentElement;
        while (parent) {
          const style = window.getComputedStyle(parent);
          if (
            style.overflowY === 'auto' ||
            style.overflowY === 'scroll' ||
            style.overflow === 'auto' ||
            style.overflow === 'scroll'
          ) {
            scrollElement = parent as HTMLDivElement;
            // Update scrollRef with the found element for future use
            scrollRef.current = scrollElement;
            break;
          }
          parent = parent.parentElement;
        }
      }

      // If no scroll element found, use null (viewport as root)
      if (!scrollElement) {
        console.warn('useInfiniteScroll: No scrollable container found, using viewport as root');
      }

      const observer = new IntersectionObserver(
        (entries) => {
          const [entry] = entries;
          if (entry?.isIntersecting) {
            // For reverse scrolling, ignore the first intersection when sentinel is initially visible at top
            if (ignoreFirstIntersectionRef.current && isReverse) {
              // Reset the flag immediately so subsequent intersections work
              ignoreFirstIntersectionRef.current = false;
              return;
            }
            
            loadMore();
          }
        },
        {
          root: scrollElement ?? null,
          rootMargin: effectiveRootMargin,
          threshold: 0.1,
        }
      );

      observerRef.current = observer;
      observer.observe(sentinel);
    });

    return () => {
      cancelAnimationFrame(rafId);
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }
    };
  }, [autoLoadMore, hasMore, isEnabled, loadMore, effectiveRootMargin, items.length, isReverse]);

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

  // Reset and reload when search or filters change (debounced)
  useEffect(() => {
    if (autoLoad && isEnabled) {
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, debouncedFilters, autoLoad, isEnabled, reset]);

  // Reload when initial params change or component mounts
  useEffect(() => {
    currentPageRef.current = 0;
    setItems([]);
    setHasMore(true);
    setTotal(undefined);
    setError(null);

    if (autoLoad && isEnabled) {
      fetchData(false);
    } else {
      setInitialLoading(false);
      setLoading(false);
      setLoadingMore(false);
    }
  }, [initialParamsKey, autoLoad, isEnabled, fetchData]);

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