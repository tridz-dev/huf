# Dashboard Framework - Quick Start Guide

## Creating a New Page (3 Minutes)

### Step 1: Import Framework Components
```tsx
import { PageLayout, FilterBar, GridView, ItemCard } from '@/components/dashboard';
import { usePageData } from '@/hooks/dashboard/usePageData';
```

### Step 2: Define Your Data Type
```tsx
interface MyItem {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'inactive';
}

const items: MyItem[] = [
  { id: '1', name: 'Item 1', description: 'First item', status: 'active' },
  // ... more items
];
```

### Step 3: Use the Framework
```tsx
export function MyNewPage() {
  const { data, search, setSearch, filters, setFilters } = usePageData<MyItem>({
    initialData: items,
    searchFields: ['name', 'description'],
    filterFn: (item, filters) => {
      if (filters.status && filters.status !== 'all') {
        return item.status === filters.status;
      }
      return true;
    },
  });

  return (
    <PageLayout
      subtitle="Manage your items"
      filters={
        <FilterBar
          searchPlaceholder="Search items..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: [
                { label: 'All', value: 'all' },
                { label: 'Active', value: 'active' },
                { label: 'Inactive', value: 'inactive' },
              ],
              onChange: (value) => setFilters({ ...filters, status: value }),
            },
          ]}
        />
      }
    >
      <GridView
        items={data}
        columns={{ sm: 1, md: 2, lg: 3 }}
        renderItem={(item) => (
          <ItemCard
            title={item.name}
            description={item.description}
            status={{ label: item.status }}
            onClick={() => console.log('Clicked', item.id)}
          />
        )}
        keyExtractor={(item) => item.id}
      />
    </PageLayout>
  );
}
```

### Step 4: Add to Router
```tsx
// In App.tsx
<Route
  path="/my-page"
  element={
    <UnifiedLayout headerActions={<MyPageHeaderActions />}>
      <MyNewPage />
    </UnifiedLayout>
  }
/>
```

## Component Cheat Sheet

### PageLayout
```tsx
<PageLayout
  subtitle="Page description"
  filters={<FilterBar ... />}
  toolbar={<Button>Action</Button>}
  className="custom-class"
>
  {children}
</PageLayout>
```

### GridView
```tsx
<GridView
  items={data}
  columns={{ sm: 1, md: 2, lg: 3, xl: 4 }}
  gap={4}
  loading={false}
  emptyState={<div>No items</div>}
  renderItem={(item) => <ItemCard {...item} />}
  keyExtractor={(item) => item.id}
/>
```

### ItemCard
```tsx
<ItemCard
  title="Card Title"
  description="Card description"
  status={{ label: 'Active', variant: 'default' }}
  metadata={[
    { label: 'Field 1', value: 'Value 1' },
    { label: 'Field 2', value: 'Value 2', icon: IconComponent },
  ]}
  actions={[
    { icon: Edit, label: 'Edit', onClick: () => {} },
    { icon: Delete, label: 'Delete', onClick: () => {} },
  ]}
  onClick={() => {}}
  className="custom-class"
/>
```

### StatCard
```tsx
<StatCard
  title="Total Users"
  value="1,234"
  description="Registered users"
  icon={Users}
  badge={<Badge>+12%</Badge>}
  trend={{ value: '+12% from last month', direction: 'up' }}
  onClick={() => {}}
  className="bg-gradient-to-t from-primary/5 to-card"
/>
```

### FilterBar
```tsx
<FilterBar
  searchPlaceholder="Search..."
  searchValue={search}
  onSearchChange={setSearch}
  filters={[
    {
      label: 'Filter Label',
      value: currentValue,
      options: [
        { label: 'Option 1', value: 'opt1' },
        { label: 'Option 2', value: 'opt2' },
      ],
      onChange: (value) => handleChange(value),
    },
  ]}
  actions={<Button>Action</Button>}
/>
```

### usePageData Hook
```tsx
const {
  data,           // Filtered data
  allData,        // All data (unfiltered)
  loading,        // Loading state
  error,          // Error state
  search,         // Current search value
  setSearch,      // Set search value
  filters,        // Current filters
  setFilters,     // Set filters
  setData,        // Update data
} = usePageData<T>({
  fetchFn: async () => { ... },        // Optional: fetch function
  initialData: [],                      // Optional: initial data
  searchFields: ['name', 'description'], // Fields to search
  filterFn: (item, filters) => true,   // Optional: custom filter
});
```

## Common Patterns

### Pattern 1: Simple List Page
```tsx
export function SimplePage() {
  return (
    <PageLayout subtitle="Simple list">
      <GridView
        items={items}
        columns={{ sm: 1, md: 2, lg: 3 }}
        renderItem={(item) => <ItemCard title={item.name} />}
        keyExtractor={(item) => item.id}
      />
    </PageLayout>
  );
}
```

### Pattern 2: Page with Search
```tsx
export function SearchablePage() {
  const { data, search, setSearch } = usePageData({
    initialData: items,
    searchFields: ['name'],
  });

  return (
    <PageLayout
      subtitle="Searchable list"
      filters={
        <FilterBar searchValue={search} onSearchChange={setSearch} />
      }
    >
      <GridView items={data} ... />
    </PageLayout>
  );
}
```

### Pattern 3: Dashboard with Metrics
```tsx
export function DashboardPage() {
  return (
    <PageLayout subtitle="Dashboard overview">
      <GridView
        items={metrics}
        columns={{ sm: 1, md: 2, lg: 4 }}
        renderItem={(metric) => (
          <StatCard
            title={metric.title}
            value={metric.value}
            icon={metric.icon}
            badge={metric.badge}
          />
        )}
        keyExtractor={(metric) => metric.id}
      />
    </PageLayout>
  );
}
```

### Pattern 4: Async Data Loading
```tsx
export function AsyncPage() {
  const { data, loading } = usePageData({
    fetchFn: async () => {
      const response = await fetch('/api/items');
      return response.json();
    },
  });

  return (
    <PageLayout subtitle="Loaded from API">
      <GridView items={data} loading={loading} ... />
    </PageLayout>
  );
}
```

## Tips & Tricks

### Tip 1: Custom Empty State
```tsx
<GridView
  items={data}
  emptyState={
    <div className="text-center py-12">
      <h3 className="text-lg font-semibold">No items found</h3>
      <p className="text-muted-foreground">Try adjusting your filters</p>
      <Button className="mt-4">Create New Item</Button>
    </div>
  }
  ...
/>
```

### Tip 2: Custom Card Content
```tsx
<ItemCard
  title={item.name}
  footer={
    <div className="flex items-center gap-2">
      <Avatar src={item.avatar} />
      <span>{item.owner}</span>
    </div>
  }
  ...
/>
```

### Tip 3: Multiple Sections
```tsx
<PageLayout subtitle="Multiple sections">
  <PageSection title="Active Items">
    <GridView items={activeItems} ... />
  </PageSection>

  <PageSection title="Archived Items">
    <GridView items={archivedItems} ... />
  </PageSection>
</PageLayout>
```

### Tip 4: Responsive Columns
```tsx
// Mobile: 1 col, Tablet: 2 cols, Desktop: 3 cols, Wide: 4 cols
<GridView columns={{ sm: 1, md: 2, lg: 3, xl: 4 }} ... />

// Mobile: 1 col, Desktop: 2 cols (tablet same as desktop)
<GridView columns={{ sm: 1, lg: 2 }} ... />
```

## Need Help?

- **Full Documentation**: See `DASHBOARD_FRAMEWORK.md`
- **Architecture Details**: See `REFACTORING_PROPOSAL.md`
- **Implementation Story**: See `IMPLEMENTATION_SUMMARY.md`
- **Example Pages**: Check `AgentsPage.tsx` and `HomePage.tsx`

Happy building! 🚀
