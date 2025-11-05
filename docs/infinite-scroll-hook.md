# Infinite Scroll Hook Documentation

## Overview

The `useInfiniteScroll` hook provides a reusable solution for implementing infinite scrolling pagination with search, filters, and debouncing. It's designed to work seamlessly with any API that supports pagination.

## Features

- ✅ **Infinite Scrolling**: Automatically loads more data when scrolling near the bottom
- ✅ **Pagination**: Handles page-based pagination internally
- ✅ **Search**: Built-in search with debouncing
- ✅ **Filters**: Support for multiple filter parameters with debouncing
- ✅ **Loading States**: Separate states for initial load and loading more
- ✅ **Error Handling**: Comprehensive error handling and state management
- ✅ **Type Safe**: Fully typed with TypeScript generics
- ✅ **Debouncing**: Configurable debounce delay for search and filters

## Installation

The hook is already available in `frontend/src/hooks/useInfiniteScroll.ts`.

## Basic Usage

```tsx
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';

function MyComponent() {
  const {
    items,
    hasMore,
    loading,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    filters,
    setFilter,
    scrollRef,
    total,
  } = useInfiniteScroll({
    fetchFn: async (params) => {
      const response = await fetch(`/api/items?page=${params.page}&limit=${params.limit}&search=${params.search}`);
      const data = await response.json();
      return {
        data: data.items,
        hasMore: data.hasMore,
        total: data.total,
      };
    },
    initialParams: { category: 'electronics' },
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
    threshold: 200,
  });

  return (
    <div ref={scrollRef} className="overflow-auto h-[600px]">
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search..."
      />
      {initialLoading ? (
        <div>Loading...</div>
      ) : (
        <>
          {items.map((item) => (
            <div key={item.id}>{item.name}</div>
          ))}
          {loadingMore && <div>Loading more...</div>}
          {!hasMore && items.length > 0 && <div>No more items</div>}
        </>
      )}
    </div>
  );
}
```

## API Reference

### Hook Options

```typescript
interface UseInfiniteScrollOptions<TParams extends PaginationParams, TItem> {
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
   * Threshold from bottom of container (in pixels) to trigger load more
   * @default 200
   */
  threshold?: number;
}
```

### Return Values

```typescript
interface UseInfiniteScrollReturn<TItem> {
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
   * Ref to attach to scrollable container element
   */
  scrollRef: React.RefObject<HTMLElement>;

  /**
   * Total number of items (if provided by API)
   */
  total: number | undefined;
}
```

## Advanced Examples

### With Filters

```tsx
const {
  items,
  filters,
  setFilter,
  setFilters,
} = useInfiniteScroll({
  fetchFn: async (params) => {
    const response = await getAgentTriggers({
      agentName: params.agentName,
      page: params.page,
      limit: params.limit,
      type: params.type,
      status: params.status,
      search: params.search,
    });
    return {
      data: response.items,
      hasMore: response.hasMore,
      total: response.total,
    };
  },
  initialParams: { agentName: 'agent-123' },
});

// Set a single filter
<Select onValueChange={(value) => setFilter('type', value)}>
  <SelectItem value="all">All Types</SelectItem>
  <SelectItem value="Schedule">Schedule</SelectItem>
</Select>

// Set multiple filters at once
setFilters({ type: 'Schedule', status: 'active' });
```

### Without Auto-Load

```tsx
const { items, reset } = useInfiniteScroll({
  fetchFn: fetchData,
  autoLoad: false,
});

// Load data manually
useEffect(() => {
  reset();
}, [someCondition]);
```

### Custom Threshold

```tsx
const { items, scrollRef } = useInfiniteScroll({
  fetchFn: fetchData,
  threshold: 500, // Load more when 500px from bottom
});
```

## Best Practices

1. **Always attach scrollRef**: The hook requires a scrollable container element to detect when to load more data.

2. **Handle loading states**: Show appropriate loading indicators for `initialLoading` and `loadingMore` states.

3. **Debounce delay**: Adjust `debounceMs` based on your API response time. Longer delays reduce API calls but may feel slower.

4. **Page size**: Choose an appropriate `pageSize` based on your data size and API performance. Common values are 20-50 items.

5. **Threshold**: Set `threshold` based on your item height. Larger items may need a larger threshold.

6. **Error handling**: Always check the `error` state and display appropriate error messages to users.

7. **Reset on filter changes**: The hook automatically resets when filters change, but you can manually call `reset()` if needed.

## Integration with Frappe API

When using with Frappe's `db.getDocList`, ensure your API function returns the correct format:

```typescript
async function fetchTriggers(params: GetAgentTriggersParams) {
  const triggers = await db.getDocList('Agent Trigger', {
    fields: ['name', 'trigger_name'],
    filters: [['agent', '=', params.agentName]],
    limit: params.limit,
    limit_start: params.start,
  });

  return {
    data: triggers,
    hasMore: triggers.length === params.limit, // Adjust based on your logic
    total: undefined, // Or fetch total separately
  };
}
```

## Troubleshooting

### Data not loading
- Check that `autoLoad` is `true` or call `reset()` manually
- Verify `fetchFn` returns the correct format: `{ data, hasMore, total? }`
- Check browser console for errors

### Infinite scroll not triggering
- Ensure `scrollRef` is attached to a scrollable container
- Check that the container has `overflow-auto` or `overflow-scroll`
- Verify `hasMore` is `true` when more data is available
- Check that `threshold` is appropriate for your content height

### Filters not working
- Ensure filters are passed correctly in `fetchFn`
- Check that debouncing isn't causing delays
- Verify filter values match what your API expects

### Performance issues
- Reduce `pageSize` if loading too many items at once
- Increase `debounceMs` to reduce API calls
- Consider implementing virtual scrolling for very large lists

## Related Hooks

- `useDebounce`: Used internally for debouncing search and filters
- `usePageData`: Alternative hook for simple pagination without infinite scroll

