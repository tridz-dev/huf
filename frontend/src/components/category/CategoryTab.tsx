import { Plus, Tag, Trash2 } from 'lucide-react';
import * as Icons from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { TABLE_ICON_MAP } from '@/data/tableIcons';

interface Category {
  name: string;
  category_name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_category?: string;
}

interface CategoryTabProps {
  selectedCategories: Category[];
  onAddCategories: () => void;
  onRemoveCategory: (name: string) => void;
  onEditCategory: (category: Category) => void;
}

export function CategoryTab({
  selectedCategories,
  onAddCategories,
  onRemoveCategory,
  onEditCategory,
}: CategoryTabProps) {
  const getCategoryIcon = (iconName?: string) => {
    if (!iconName) return Tag;
    return TABLE_ICON_MAP[iconName] || (Icons[iconName as keyof typeof Icons] as React.ElementType) || Tag;
  };

  const getCategoryColor = (color?: string) => {
    if (!color) return '#6366f1';
    return color;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Tag className="w-5 h-5" />
              Categories
            </CardTitle>
            <CardDescription>
              Organize your prompt using categories
            </CardDescription>
          </div>

          <Button size="sm" variant="outline" onClick={onAddCategories}>
            <Plus className="w-4 h-4 mr-2" />
            Add Category
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {selectedCategories.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground mb-2">
              No categories selected.
            </p>
            <Button onClick={onAddCategories} variant="outline">
              <Plus className="w-4 h-4 mr-2" />
              Add Category
            </Button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {selectedCategories.map((cat) => {
              const CategoryIcon = getCategoryIcon(cat.icon);
              const bgColor = getCategoryColor(cat.color);

              return (
                <div
                  key={cat.name}
                  className="group p-2 border rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <CategoryIcon className="w-4 h-4" style={{ color: bgColor }} />
                      {cat.color && (
                        <span
                          className="w-2 h-2 rounded-full border"
                          style={{ backgroundColor: bgColor }}
                        />
                      )}
                      <span className="text-xs font-semibold truncate">
                        {cat.category_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onEditCategory(cat)}
                        title="Edit category"
                        className="h-6 w-6 p-0"
                      >
                        <Icons.Edit className="w-3 h-3" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onRemoveCategory(cat.name)}
                        title="Remove category"
                        className="h-6 w-6 p-0"
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                  {cat.description && (
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      {cat.description}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}