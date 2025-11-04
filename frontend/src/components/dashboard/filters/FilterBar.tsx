import { ReactNode, useState } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface FilterOption {
  label: string;
  value: string;
}

interface Filter {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}

interface FilterBarProps {
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  filters?: Filter[];
  actions?: ReactNode;
  collapsibleSearch?: boolean;
}

export function FilterBar({
  searchPlaceholder = 'Search...',
  searchValue,
  onSearchChange,
  filters = [],
  actions,
  collapsibleSearch = false,
}: FilterBarProps) {
  const [isSearchExpanded, setIsSearchExpanded] = useState(false);

  const handleToggleSearch = () => {
    setIsSearchExpanded(!isSearchExpanded);
    if (isSearchExpanded && onSearchChange) {
      onSearchChange('');
    }
  };

  return (
    <div className="flex gap-4 items-center">
      {onSearchChange && (
        <>
          {collapsibleSearch ? (
            <div className="flex items-center gap-2">
              {isSearchExpanded ? (
                <div className="relative flex items-center gap-2">
                  <div className="relative flex-1 min-w-[200px]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder={searchPlaceholder}
                      className="pl-9 pr-9"
                      value={searchValue}
                      onChange={(e) => onSearchChange(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-10 w-10"
                    onClick={handleToggleSearch}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  size="icon"
                  className="h-10 w-10"
                  onClick={handleToggleSearch}
                >
                  <Search className="w-4 h-4" />
                </Button>
              )}
            </div>
          ) : (
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder={searchPlaceholder}
                className="pl-9"
                value={searchValue}
                onChange={(e) => onSearchChange(e.target.value)}
              />
            </div>
          )}
        </>
      )}

      {filters.map((filter, index) => (
        <Select
          key={index}
          value={filter.value}
          onValueChange={filter.onChange}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder={filter.placeholder || filter.label} />
          </SelectTrigger>
          <SelectContent>
            {filter.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}

      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
