import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface CategoryFilterProps {
  value: string;
  categories: string[];
  onChange: (value: string) => void;
}

/** "All categories" dropdown for the Integrations screens. */
export function CategoryFilter({ value, categories, onChange }: CategoryFilterProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        aria-label="Category"
        className="h-control-sm w-auto min-w-[10rem] gap-2 rounded-lg border-line bg-panel px-3 py-0 text-ui-text shadow-none"
        data-testid="integration-category-filter"
      >
        <SelectValue placeholder="All categories" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All categories</SelectItem>
        {categories.map((category) => (
          <SelectItem key={category} value={category}>
            {category}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
