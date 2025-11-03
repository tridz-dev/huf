# Contributing to HufAI - UI Framework Guide

Welcome to the HufAI UI Framework! This guide will show you how to extend the platform with new pages, components, and features using our dashboard framework.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Creating a New Page](#creating-a-new-page)
3. [Adding Header Actions](#adding-header-actions)
4. [Adding Sidebar Navigation](#adding-sidebar-navigation)
5. [Using Framework Components](#using-framework-components)
6. [Working with Data](#working-with-data)
7. [Creating Custom Cards](#creating-custom-cards)
8. [Adding Filters](#adding-filters)
9. [Styling Guidelines](#styling-guidelines)
10. [Best Practices](#best-practices)

---

## Quick Start

### Prerequisites

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open browser at http://localhost:5173
```

### Framework Structure

```
src/
├── components/dashboard/    # Framework components
│   ├── layouts/             # PageLayout, PageSection
│   ├── views/               # GridView (ListView, KanbanView coming soon)
│   ├── cards/               # BaseCard, StatCard, ItemCard
│   └── filters/             # FilterBar
├── hooks/dashboard/         # usePageData
├── pages/                   # Your pages go here
└── layouts/                 # UnifiedLayout, UnifiedHeader, UnifiedSidebar
```

---

## Creating a New Page

### Step 1: Create the Page Component

Create a new file in `src/pages/`:

```tsx
// src/pages/ProjectsPage.tsx
import { PageLayout, FilterBar, GridView, ItemCard } from '@/components/dashboard';
import { usePageData } from '@/hooks/dashboard/usePageData';
import { Folder, Calendar, Users } from 'lucide-react';

interface Project {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'archived' | 'draft';
  team: string;
  createdAt: string;
}

const projects: Project[] = [
  {
    id: '1',
    name: 'AI Agent Platform',
    description: 'Build and deploy AI agents',
    status: 'active',
    team: 'Engineering',
    createdAt: '2024-01-15',
  },
  // ... more projects
];

export function ProjectsPage() {
  const { data, search, setSearch, filters, setFilters } = usePageData<Project>({
    initialData: projects,
    searchFields: ['name', 'description'],
    filterFn: (project, filters) => {
      if (filters.status && filters.status !== 'all') {
        return project.status === filters.status;
      }
      return true;
    },
  });

  return (
    <PageLayout
      subtitle="Manage your projects and teams"
      filters={
        <FilterBar
          searchPlaceholder="Search projects..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: [
                { label: 'All', value: 'all' },
                { label: 'Active', value: 'active' },
                { label: 'Archived', value: 'archived' },
                { label: 'Draft', value: 'draft' },
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
        renderItem={(project) => (
          <ItemCard
            title={project.name}
            description={project.description}
            status={{
              label: project.status,
              variant: project.status === 'active' ? 'default' : 'secondary',
            }}
            metadata={[
              { label: 'Team', value: project.team, icon: Users },
              { label: 'Created', value: project.createdAt, icon: Calendar },
            ]}
            onClick={() => console.log('Project clicked', project.id)}
          />
        )}
        keyExtractor={(project) => project.id}
      />
    </PageLayout>
  );
}
```

### Step 2: Add Route

Update `src/App.tsx`:

```tsx
import { ProjectsPage } from './pages/ProjectsPage';

// Inside your Routes component:
<Route
  path="/projects"
  element={
    <UnifiedLayout headerActions={<ProjectsHeaderActions />}>
      <ProjectsPage />
    </UnifiedLayout>
  }
/>
```

### Step 3: Test Your Page

Navigate to `http://localhost:5173/projects` and you should see your new page!

---

## Adding Header Actions

Header actions are the buttons that appear in the top right of the page (like "New Agent", "Run", etc.)

### Create Header Actions Component

```tsx
// src/components/ProjectsHeaderActions.tsx
import { Button } from '@/components/ui/button';
import { Plus, Upload, Download } from 'lucide-react';

export function ProjectsHeaderActions() {
  return (
    <>
      <Button variant="outline" size="sm">
        <Download className="w-4 h-4 mr-2" />
        Export
      </Button>
      <Button variant="outline" size="sm">
        <Upload className="w-4 h-4 mr-2" />
        Import
      </Button>
      <Button size="sm">
        <Plus className="w-4 h-4 mr-2" />
        New Project
      </Button>
    </>
  );
}
```

### Use in Layout

```tsx
<UnifiedLayout headerActions={<ProjectsHeaderActions />}>
  <ProjectsPage />
</UnifiedLayout>
```

### Header Actions Patterns

**Single Primary Action**
```tsx
<Button size="sm">
  <Plus className="w-4 h-4 mr-2" />
  Create
</Button>
```

**Multiple Actions**
```tsx
<>
  <Button variant="outline" size="sm">Secondary</Button>
  <Button size="sm">Primary</Button>
</>
```

**With Dropdown**
```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button variant="outline" size="sm">
      <MoreVertical className="w-4 h-4" />
    </Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent align="end">
    <DropdownMenuItem>Edit</DropdownMenuItem>
    <DropdownMenuItem>Duplicate</DropdownMenuItem>
    <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

---

## Adding Sidebar Navigation

### Step 1: Update Navigation Data

Edit `src/layouts/UnifiedSidebar.tsx` to add your new page:

```tsx
const navItems = [
  {
    title: 'Home',
    url: '/',
    icon: Home,
  },
  {
    title: 'Agents',
    url: '/agents',
    icon: Bot,
  },
  {
    title: 'Flows',
    url: '/flows',
    icon: Workflow,
  },
  {
    title: 'Projects',  // NEW!
    url: '/projects',
    icon: Folder,
  },
  {
    title: 'Data',
    url: '/data',
    icon: Database,
  },
  {
    title: 'Integrations',
    url: '/integrations',
    icon: Plug,
  },
];
```

### Step 2: Import the Icon

At the top of `UnifiedSidebar.tsx`:

```tsx
import { Home, Bot, Workflow, Folder, Database, Plug } from 'lucide-react';
```

### Navigation with Sections

For grouped navigation:

```tsx
const navGroups = [
  {
    title: 'Main',
    items: [
      { title: 'Home', url: '/', icon: Home },
      { title: 'Projects', url: '/projects', icon: Folder },
    ],
  },
  {
    title: 'Automation',
    items: [
      { title: 'Agents', url: '/agents', icon: Bot },
      { title: 'Flows', url: '/flows', icon: Workflow },
    ],
  },
  {
    title: 'Resources',
    items: [
      { title: 'Data', url: '/data', icon: Database },
      { title: 'Integrations', url: '/integrations', icon: Plug },
    ],
  },
];
```

---

## Using Framework Components

### PageLayout

Universal page wrapper with consistent spacing:

```tsx
<PageLayout
  subtitle="Page description"
  filters={<FilterBar ... />}
  toolbar={<Button>Custom Action</Button>}
  className="custom-class"
>
  {children}
</PageLayout>
```

**Props:**
- `subtitle?: string` - Text below page title
- `filters?: ReactNode` - Filter components
- `toolbar?: ReactNode` - Custom toolbar content
- `className?: string` - Additional CSS classes

### PageSection

Section containers for organizing content:

```tsx
<PageSection
  title="Recent Projects"
  description="Your most recently updated projects"
  actions={
    <Button variant="ghost" size="sm">
      View All
    </Button>
  }
>
  <GridView items={recentProjects} ... />
</PageSection>
```

**Props:**
- `title?: string` - Section heading
- `description?: string` - Section description
- `actions?: ReactNode` - Action buttons
- `className?: string` - Additional CSS classes

### GridView

Responsive grid for displaying items:

```tsx
<GridView
  items={data}
  columns={{ sm: 1, md: 2, lg: 3, xl: 4 }}
  gap={4}
  loading={false}
  emptyState={<EmptyMessage />}
  renderItem={(item) => <Card {...item} />}
  keyExtractor={(item) => item.id}
  className="custom-class"
/>
```

**Props:**
- `items: T[]` - Array of items to display
- `columns?: { sm?, md?, lg?, xl? }` - Responsive column counts
- `gap?: number` - Gap between items (Tailwind scale)
- `loading?: boolean` - Show loading state
- `emptyState?: ReactNode` - Custom empty state
- `renderItem: (item: T) => ReactNode` - Render function
- `keyExtractor: (item: T) => string` - Unique key function
- `className?: string` - Additional CSS classes

### FilterBar

Search and filter controls:

```tsx
<FilterBar
  searchPlaceholder="Search..."
  searchValue={search}
  onSearchChange={setSearch}
  filters={[
    {
      label: 'Status',
      value: statusFilter,
      options: [
        { label: 'All', value: 'all' },
        { label: 'Active', value: 'active' },
      ],
      onChange: handleStatusChange,
      placeholder: 'Select status',
    },
  ]}
  actions={<Button>New Item</Button>}
/>
```

**Props:**
- `searchPlaceholder?: string` - Search input placeholder
- `searchValue?: string` - Current search value
- `onSearchChange?: (value: string) => void` - Search change handler
- `filters?: Filter[]` - Filter dropdowns
- `actions?: ReactNode` - Additional action buttons

---

## Working with Data

### usePageData Hook

Manage page data, search, and filters:

```tsx
const {
  data,           // Filtered data
  allData,        // Unfiltered data
  loading,        // Loading state
  error,          // Error state
  search,         // Search value
  setSearch,      // Set search
  filters,        // Current filters
  setFilters,     // Set filters
  setData,        // Update data
} = usePageData<MyType>({
  fetchFn: async () => {
    // Fetch from API or Supabase
    const response = await fetch('/api/items');
    return response.json();
  },
  initialData: [],
  searchFields: ['name', 'description', 'tags'],
  filterFn: (item, filters) => {
    // Custom filter logic
    if (filters.status !== 'all' && item.status !== filters.status) {
      return false;
    }
    if (filters.category && item.category !== filters.category) {
      return false;
    }
    return true;
  },
});
```

### With Supabase

```tsx
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const { data, loading } = usePageData<Project>({
  fetchFn: async () => {
    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) throw error;
    return data;
  },
  searchFields: ['name', 'description'],
});
```

### Loading States

```tsx
{loading && <div>Loading...</div>}
{error && <div>Error: {error.message}</div>}
{data && <GridView items={data} ... />}
```

Or use GridView's built-in loading state:

```tsx
<GridView
  items={data}
  loading={loading}
  emptyState={<div>No items found</div>}
  ...
/>
```

---

## Creating Custom Cards

### StatCard

For metrics and statistics:

```tsx
<StatCard
  title="Total Projects"
  value="24"
  description="Active projects"
  icon={Folder}
  badge={
    <Badge variant="outline" className="gap-1">
      <TrendingUp className="w-3 h-3" />
      +12%
    </Badge>
  }
  trend={{ value: '+3 from last month', direction: 'up' }}
  onClick={() => navigate('/projects')}
  className="bg-gradient-to-t from-primary/5 to-card"
/>
```

### ItemCard

For entities (agents, projects, etc.):

```tsx
<ItemCard
  title="AI Assistant"
  description="Handles customer support"
  status={{ label: 'Active', variant: 'default' }}
  metadata={[
    { label: 'Type', value: 'GPT-4' },
    { label: 'Runs', value: '1,234', icon: Zap },
    { label: 'Updated', value: '2 mins ago', icon: Clock },
  ]}
  actions={[
    {
      icon: Play,
      label: 'Run',
      onClick: () => handleRun(),
      variant: 'default',
    },
    {
      icon: Settings,
      label: 'Configure',
      onClick: () => handleConfigure(),
      variant: 'ghost',
    },
  ]}
  onClick={() => navigate(`/agents/${agent.id}`)}
/>
```

### BaseCard

For custom card content:

```tsx
<BaseCard onClick={() => {}} hover={true} className="p-6">
  <h3 className="text-lg font-semibold">Custom Card</h3>
  <p className="text-muted-foreground mt-2">Your custom content here</p>

  <div className="flex gap-2 mt-4">
    <Button size="sm">Action 1</Button>
    <Button size="sm" variant="outline">Action 2</Button>
  </div>
</BaseCard>
```

### Custom Card Component

Create your own card type:

```tsx
// src/components/dashboard/cards/TeamCard.tsx
import { BaseCard } from './BaseCard';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';

interface TeamCardProps {
  name: string;
  members: Array<{ name: string; avatar?: string }>;
  projectCount: number;
  onClick?: () => void;
}

export function TeamCard({ name, members, projectCount, onClick }: TeamCardProps) {
  return (
    <BaseCard onClick={onClick} className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">{name}</h3>
        <Badge variant="secondary">{projectCount} projects</Badge>
      </div>

      <div className="flex -space-x-2">
        {members.slice(0, 5).map((member, i) => (
          <Avatar key={i} className="border-2 border-background">
            <AvatarImage src={member.avatar} />
            <AvatarFallback>{member.name[0]}</AvatarFallback>
          </Avatar>
        ))}
        {members.length > 5 && (
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-muted border-2 border-background text-xs">
            +{members.length - 5}
          </div>
        )}
      </div>
    </BaseCard>
  );
}
```

---

## Adding Filters

### Simple Filter

```tsx
<FilterBar
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
```

### Multiple Filters

```tsx
<FilterBar
  searchValue={search}
  onSearchChange={setSearch}
  filters={[
    {
      label: 'Status',
      value: filters.status || 'all',
      options: statusOptions,
      onChange: (value) => setFilters({ ...filters, status: value }),
    },
    {
      label: 'Category',
      value: filters.category || 'all',
      options: categoryOptions,
      onChange: (value) => setFilters({ ...filters, category: value }),
    },
    {
      label: 'Team',
      value: filters.team || 'all',
      options: teamOptions,
      onChange: (value) => setFilters({ ...filters, team: value }),
    },
  ]}
/>
```

### Custom Filter Function

```tsx
const { data } = usePageData({
  initialData: items,
  searchFields: ['name', 'description'],
  filterFn: (item, filters) => {
    // Status filter
    if (filters.status && filters.status !== 'all') {
      if (item.status !== filters.status) return false;
    }

    // Date range filter
    if (filters.dateFrom) {
      const itemDate = new Date(item.createdAt);
      const fromDate = new Date(filters.dateFrom);
      if (itemDate < fromDate) return false;
    }

    // Array contains filter
    if (filters.tags && filters.tags.length > 0) {
      const hasTag = filters.tags.some(tag => item.tags.includes(tag));
      if (!hasTag) return false;
    }

    return true;
  },
});
```

---

## Styling Guidelines

### Tailwind Classes

Follow the 8px spacing system:

```tsx
// Spacing
<div className="p-6">           // Padding: 24px
<div className="mt-4">          // Margin top: 16px
<div className="gap-2">         // Gap: 8px

// Colors
<div className="bg-card">                    // Background
<div className="text-foreground">           // Text
<div className="text-muted-foreground">     // Muted text
<div className="border-border">             // Border

// Typography
<h1 className="text-3xl font-bold">         // Large heading
<h2 className="text-lg font-semibold">      // Section heading
<p className="text-sm text-muted-foreground"> // Small text
```

### Responsive Design

```tsx
// Mobile-first approach
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
  Mobile: 1 column
  Tablet: 2 columns
  Desktop: 3 columns
</div>

// Responsive padding
<div className="p-4 md:p-6 lg:p-8">

// Responsive text
<h1 className="text-2xl md:text-3xl lg:text-4xl">
```

### Custom Classes

Use the `cn()` utility for conditional classes:

```tsx
import { cn } from '@/lib/utils';

<div className={cn(
  'base-classes',
  isActive && 'active-classes',
  variant === 'primary' && 'primary-classes',
  className
)} />
```

### Theme Colors

```tsx
// Use CSS variables for theme support
<div className="bg-background text-foreground">
<div className="bg-card text-card-foreground">
<div className="bg-primary text-primary-foreground">
<div className="bg-secondary text-secondary-foreground">
<div className="bg-muted text-muted-foreground">
<div className="bg-destructive text-destructive-foreground">
```

---

## Best Practices

### 1. Component Organization

```
src/pages/
├── ProjectsPage.tsx           # Main page component
src/components/
├── ProjectsHeaderActions.tsx  # Header actions
├── ProjectCard.tsx            # Custom card (if needed)
```

### 2. Type Definitions

Always define interfaces for your data:

```tsx
interface Project {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'archived' | 'draft';
  team: string;
  createdAt: string;
  updatedAt: string;
}
```

### 3. Reuse Framework Components

Don't recreate what already exists:

```tsx
// ❌ Don't do this
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {items.map(item => <Card key={item.id} {...item} />)}
</div>

// ✅ Do this
<GridView
  items={items}
  columns={{ sm: 1, md: 2, lg: 3 }}
  renderItem={(item) => <ItemCard {...item} />}
  keyExtractor={(item) => item.id}
/>
```

### 4. Error Handling

Always handle errors gracefully:

```tsx
const { data, loading, error } = usePageData({
  fetchFn: async () => {
    try {
      const response = await fetch('/api/items');
      if (!response.ok) throw new Error('Failed to fetch');
      return response.json();
    } catch (error) {
      console.error('Error fetching items:', error);
      throw error;
    }
  },
});

if (error) {
  return (
    <div className="p-6 text-center">
      <p className="text-destructive">Error loading data</p>
      <Button onClick={() => window.location.reload()} className="mt-4">
        Retry
      </Button>
    </div>
  );
}
```

### 5. Accessibility

Use semantic HTML and ARIA attributes:

```tsx
<button
  aria-label="Delete project"
  onClick={handleDelete}
>
  <Trash className="w-4 h-4" />
</button>

<input
  type="search"
  placeholder="Search projects"
  aria-label="Search projects"
/>
```

### 6. Performance

Memoize expensive operations:

```tsx
import { useMemo } from 'react';

const filteredData = useMemo(() => {
  return data.filter(item => {
    // Expensive filtering logic
  });
}, [data, filters]);
```

### 7. File Size

Keep files under 300 lines. If larger, split into multiple files:

```tsx
// ProjectsPage.tsx
export { ProjectsPage } from './ProjectsPage';

// ProjectsList.tsx
export function ProjectsList({ projects }: Props) { ... }

// ProjectsFilters.tsx
export function ProjectsFilters({ ... }: Props) { ... }
```

---

## Common Patterns

### Pattern 1: Simple List Page

```tsx
export function MyPage() {
  const items = [...]; // Your data

  return (
    <PageLayout subtitle="Description">
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

### Pattern 2: Page with Search and Filters

```tsx
export function MyPage() {
  const { data, search, setSearch, filters, setFilters } = usePageData({
    initialData: items,
    searchFields: ['name'],
    filterFn: (item, filters) => { ... },
  });

  return (
    <PageLayout
      subtitle="Description"
      filters={
        <FilterBar
          searchValue={search}
          onSearchChange={setSearch}
          filters={[...]}
        />
      }
    >
      <GridView items={data} ... />
    </PageLayout>
  );
}
```

### Pattern 3: Dashboard with Stats

```tsx
export function DashboardPage() {
  return (
    <PageLayout>
      <GridView
        items={metrics}
        columns={{ sm: 1, md: 2, lg: 4 }}
        renderItem={(metric) => (
          <StatCard
            title={metric.title}
            value={metric.value}
            icon={metric.icon}
          />
        )}
        keyExtractor={(m) => m.id}
      />
    </PageLayout>
  );
}
```

### Pattern 4: Multi-Section Page

```tsx
export function MyPage() {
  return (
    <PageLayout subtitle="Description">
      <PageSection title="Recent Items">
        <GridView items={recentItems} ... />
      </PageSection>

      <PageSection title="All Items" actions={<Button>View All</Button>}>
        <GridView items={allItems} ... />
      </PageSection>
    </PageLayout>
  );
}
```

---

## Resources

### Documentation
- **Agents.md** - Complete platform documentation
- **docs/ARCHITECTURE.md** - Flow builder architecture
- **docs/FEATURES.md** - Flow builder features
- **docs/DASHBOARD_FRAMEWORK.md** - Detailed framework docs
- **docs/QUICK_START.md** - Quick reference guide

### Component Libraries
- [shadcn/ui](https://ui.shadcn.com/) - UI component documentation
- [Lucide Icons](https://lucide.dev/) - Icon reference
- [Tailwind CSS](https://tailwindcss.com/docs) - Styling documentation
- [React Flow](https://reactflow.dev/) - Flow builder documentation

### Getting Help

1. Check existing pages (AgentsPage, HomePage) for examples
2. Read the QUICK_START.md guide
3. Check shadcn/ui docs for component APIs
4. Review this CONTRIBUTE.md for patterns

---

## Checklist for New Pages

- [ ] Create page component in `src/pages/`
- [ ] Define TypeScript interface for data
- [ ] Use PageLayout for consistent structure
- [ ] Implement search and filters with usePageData
- [ ] Use framework components (GridView, ItemCard, etc.)
- [ ] Create header actions component
- [ ] Add route in App.tsx
- [ ] Update sidebar navigation
- [ ] Test responsive design (mobile, tablet, desktop)
- [ ] Test search and filter functionality
- [ ] Check accessibility (keyboard navigation, screen reader)
- [ ] Verify dark mode support
- [ ] Run `npm run build` to ensure no errors

---

## Quick Reference

### Import Statements

```tsx
// Framework components
import {
  PageLayout,
  PageSection,
  GridView,
  FilterBar,
  BaseCard,
  StatCard,
  ItemCard,
} from '@/components/dashboard';

// Hooks
import { usePageData } from '@/hooks/dashboard/usePageData';

// UI components
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';

// Icons
import { Plus, Edit, Trash } from 'lucide-react';

// Routing
import { useNavigate } from 'react-router-dom';

// Utils
import { cn } from '@/lib/utils';
```

---

**Happy Contributing!** 🚀

If you have questions or need help, refer to the documentation in the `docs/` folder or check existing pages for examples.
