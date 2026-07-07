import { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { SkeletonGridView } from './SkeletonGridView';

export interface GridViewColumns {
  sm?: number;
  md?: number;
  lg?: number;
  xl?: number;
}

interface GridViewProps<T> {
  items: T[];
  renderItem: (item: T) => ReactNode;
  columns?: GridViewColumns;
  gap?: number;
  loading?: boolean;
  emptyState?: ReactNode;
  keyExtractor: (item: T) => string;
  className?: string;
}

const defaultColumns: GridViewColumns = {
  sm: 1,
  md: 2,
  lg: 3,
};

const columnMap: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-4',
  5: 'grid-cols-5',
  6: 'grid-cols-6',
};

const mdColumnMap: Record<number, string> = {
  1: 'md:grid-cols-1',
  2: 'md:grid-cols-2',
  3: 'md:grid-cols-3',
  4: 'md:grid-cols-4',
  5: 'md:grid-cols-5',
  6: 'md:grid-cols-6',
};

const lgColumnMap: Record<number, string> = {
  1: 'lg:grid-cols-1',
  2: 'lg:grid-cols-2',
  3: 'lg:grid-cols-3',
  4: 'lg:grid-cols-4',
  5: 'lg:grid-cols-5',
  6: 'lg:grid-cols-6',
};

const xlColumnMap: Record<number, string> = {
  1: 'xl:grid-cols-1',
  2: 'xl:grid-cols-2',
  3: 'xl:grid-cols-3',
  4: 'xl:grid-cols-4',
  5: 'xl:grid-cols-5',
  6: 'xl:grid-cols-6',
};

const gapMap: Record<number, string> = {
  0: 'gap-0',
  1: 'gap-1',
  2: 'gap-2',
  3: 'gap-3',
  4: 'gap-4',
  5: 'gap-5',
  6: 'gap-6',
  8: 'gap-8',
};

export function getGridClasses(columns: GridViewColumns, gap: number = 4): string {
  const classes = ['grid'];

  if (columns.sm && columnMap[columns.sm]) {
    classes.push(columnMap[columns.sm]);
  }
  if (columns.md && mdColumnMap[columns.md]) {
    classes.push(mdColumnMap[columns.md]);
  }
  if (columns.lg && lgColumnMap[columns.lg]) {
    classes.push(lgColumnMap[columns.lg]);
  }
  if (columns.xl && xlColumnMap[columns.xl]) {
    classes.push(xlColumnMap[columns.xl]);
  }

  if (gapMap[gap]) {
    classes.push(gapMap[gap]);
  }

  return classes.join(' ');
}

export function GridView<T>({
  items,
  renderItem,
  columns = defaultColumns,
  gap = 4,
  loading = false,
  emptyState,
  keyExtractor,
  className,
}: GridViewProps<T>) {
  if (loading) {
    return <SkeletonGridView columns={columns} gap={gap} className={className} />;
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        {emptyState || (
          <div className="text-center text-muted-foreground">
            <p>No items to display</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={cn(getGridClasses(columns, gap), className)}>
      {items.map((item) => (
        <div key={keyExtractor(item)}>
          {renderItem(item)}
        </div>
      ))}
    </div>
  );
}
