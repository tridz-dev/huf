import { useEffect, useState, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { createCategory, updateCategory, deleteCategory } from '@/services/categoryApi';
import * as Icons from 'lucide-react';
import { Edit, Trash2 } from 'lucide-react';
import { TABLE_ICONS, TABLE_ICON_MAP } from '@/data/tableIcons';

interface Category {
  name: string;
  category_name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_category?: string;
}

interface CategoryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  selected: Category[];
  onSave: (categories: Category[]) => void;
  refreshCategories: () => Promise<void>;
  onDeleteCategory?: (categoryName: string) => void;
  editCategory?: Category | null;
  onEditComplete?: () => void;
}

export function CategoryModal({
  open,
  onOpenChange,
  categories,
  selected,
  onSave,
  refreshCategories,
  onDeleteCategory,
  editCategory,
  onEditComplete,
}: CategoryModalProps) {
  const [localCategories, setLocalCategories] = useState<Category[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  const [newCategoryData, setNewCategoryData] = useState({
    category_name: '',
    description: '',
    icon: '',
    color: '#6366F1',
    parent_category: '',
  });

  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [activeTab, setActiveTab] = useState('list');

  const [deletingCategory, setDeletingCategory] = useState<string | null>(null);

  // ✅ Sync state
  useEffect(() => {
    if (open) {
      setLocalCategories(categories);
      setSelectedIds(selected.map((c) => c.name));
      setSearchQuery(''); // Reset search when modal opens
      setEditingCategory(null); // Reset editing state
      setActiveTab('list'); // Reset to list tab
      setNewCategoryData({
        category_name: '',
        description: '',
        icon: '',
        color: '#6366F1',
        parent_category: '',
      }); // Reset form
    }
  }, [open, categories, selected]);

  const handleEditCategory = useCallback((category: Category) => {
    setEditingCategory(category);
    setActiveTab('create'); // Switch to create/edit tab
    setNewCategoryData({
      category_name: category.category_name,
      description: category.description || '',
      icon: category.icon || '',
      color: category.color || '#6366F1',
      parent_category: category.parent_category || '',
    });
  }, []);

  useEffect(() => {
    if (editCategory) {
      handleEditCategory(editCategory);
    }
  }, [editCategory, handleEditCategory]);

  // ✅ Filter categories based on search query
  const filteredCategories = localCategories.filter((cat) =>
    cat.category_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (cat.description && cat.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );



  // ✅ Toggle selection
  const toggleCategory = (name: string) => {
    setSelectedIds((prev) =>
      prev.includes(name)
        ? prev.filter((id) => id !== name)
        : [...prev, name]
    );
  };

  // ✅ Save
  const handleSave = () => {
    const selectedCategories = localCategories.filter((c) =>
      selectedIds.includes(c.name)
    );
    onSave(selectedCategories);
    onOpenChange(false);
  };

  // ✅ Delete
  const handleDelete = async (categoryName: string) => {
    if (onDeleteCategory) {
      onDeleteCategory(categoryName);
      return;
    }

    // Fallback: handle delete directly
    try {
      setDeletingCategory(categoryName);
      await deleteCategory(categoryName);
      setLocalCategories((prev) => prev.filter((c) => c.name !== categoryName));
      setSelectedIds((prev) => prev.filter((id) => id !== categoryName));
      await refreshCategories();
      toast.success('Category deleted');
    } catch (error) {
      console.error(error);
      toast.error('Failed to delete category', {
        description: 'Please try again',
      });
    } finally {
      setDeletingCategory(null);
    }
  };

  const handleCreate = async () => {
  try {
    if (!newCategoryData.category_name.trim()) {
      toast.error('Category name is required');
      return;
    }

    if (editingCategory) {
      // Update existing category
      const updated = await updateCategory(editingCategory.name, {
        category_name: newCategoryData.category_name,
        description: newCategoryData.description,
        icon: newCategoryData.icon,
        color: newCategoryData.color,
        parent_category: newCategoryData.parent_category || undefined,
      });

      // update UI immediately (ensure category_name updates even if backend returns unchanged title)
      const finalName =
        updated.name ||
        newCategoryData.category_name ||
        editingCategory.name;
      const edited: Category = {
        ...updated,
        name: finalName,
        category_name: newCategoryData.category_name,
        description: newCategoryData.description,
        icon: newCategoryData.icon,
        color: newCategoryData.color,
        parent_category: newCategoryData.parent_category || undefined,
      };

      setLocalCategories((prev) =>
        prev.map((cat) => (cat.name === editingCategory.name ? edited : cat))
      );

      setSelectedIds((prev) =>
        prev.map((id) => (id === editingCategory.name ? finalName : id))
      );

      await refreshCategories();

      // clear edit mode and form
      setEditingCategory(null);
      setActiveTab('list');
      setNewCategoryData({
        category_name: '',
        description: '',
        icon: '',
        color: '#6366F1',
        parent_category: '',
      });

      onEditComplete?.();
      toast.success('Category updated');
    } else {
      // Create new category
      const created = await createCategory({
        category_name: newCategoryData.category_name,
        description: newCategoryData.description,
        icon: newCategoryData.icon,
        color: newCategoryData.color,
        parent_category: newCategoryData.parent_category || undefined,
      });

      // update UI immediately
      setLocalCategories((prev) => [...prev, created]);

      // auto select
      setSelectedIds((prev) =>
        prev.includes(created.name) ? prev : [...prev, created.name]
      );

      await refreshCategories();

      // reset form
      setNewCategoryData({
        category_name: '',
        description: '',
        icon: '',
        color: '#6366F1',
        parent_category: '',
      });

      toast.success('Category created');
    }
  } catch (error) {
    console.error(error);
    toast.error(editingCategory ? 'Failed to update category' : 'Failed to create category', {
      description: 'Please try again',
    });
  }
};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {editingCategory
              ? `Edit Category: ${newCategoryData.category_name || editingCategory.category_name}`
              : activeTab === 'create'
              ? 'Add New Category'
              : 'Manage Categories'}
          </DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-2 bg-muted p-1 rounded-lg">
            <TabsTrigger value="list">Categories</TabsTrigger>
            <TabsTrigger value="create">{editingCategory ? 'Edit' : 'Add New'}</TabsTrigger>
          </TabsList>

          {/* ================= LIST TAB ================= */}
          <TabsContent value="list" className="mt-6">
            <div className="max-h-96 overflow-y-auto space-y-3 pr-2">
              {/* Search Input */}
              {localCategories.length > 0 && (
                <div className="space-y-2">
                  <Input
                    placeholder="Search categories..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full"
                  />
                </div>
              )}

              {localCategories.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-6">
                  No categories yet.
                  <div className="text-xs mt-1">
                    Create your first category →
                  </div>
                </div>
              ) : filteredCategories.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-6">
                  No categories match your search.
                  <div className="text-xs mt-1">
                    Try a different search term
                  </div>
                </div>
              ) : (
                <>
                  {selectedIds.length > 0 && (
                    <div>
                      <div className="mb-3 text-sm font-medium">Selected categories</div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
                        {localCategories
                          .filter((cat) => selectedIds.includes(cat.name))
                          .map((cat) => {
                            const Icon = cat.icon
                              ? TABLE_ICON_MAP[cat.icon] || (Icons[cat.icon as keyof typeof Icons] as React.ElementType)
                              : null;

                            return (
                              <div
                                key={`selected-${cat.name}`}
                                className="p-2 border rounded-lg bg-muted/30"
                              >
                                <div className="flex items-center gap-2 mb-1">
                                  {Icon ? (
                                    <Icon className="w-4 h-4" />
                                  ) : (
                                    <div className="w-4 h-4 rounded bg-muted" />
                                  )}
                                  {cat.color && (
                                    <span
                                      className="w-2 h-2 rounded-full border"
                                      style={{ backgroundColor: cat.color }}
                                    />
                                  )}
                                  <span className="text-xs font-semibold truncate">
                                    {cat.category_name}
                                  </span>
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
                    </div>
                  )}

                  {filteredCategories.map((cat) => {
                    const Icon = cat.icon
                      ? TABLE_ICON_MAP[cat.icon] || (Icons[cat.icon as keyof typeof Icons] as React.ElementType)
                      : null;

                    return (
                      <div
                        key={cat.name}
                        className={`group flex items-center gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer ${
                          selectedIds.includes(cat.name) ? 'border-primary bg-primary/5' : ''
                        }`}
                        onClick={() => toggleCategory(cat.name)}
                      >
                        {/* Checkbox */}
                        <div onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selectedIds.includes(cat.name)}
                            onCheckedChange={() => toggleCategory(cat.name)}
                          />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3">
                            {/* Icon */}
                            {Icon ? (
                              <Icon className="w-5 h-5 text-muted-foreground" />
                            ) : (
                              <div className="w-5 h-5 rounded bg-muted flex items-center justify-center">
                                <span className="text-xs text-muted-foreground">?</span>
                              </div>
                            )}

                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 whitespace-nowrap">
                                {cat.color && (
                                  <div
                                    className="w-3 h-3 rounded-full border border-border"
                                    style={{ backgroundColor: cat.color }}
                                  />
                                )}
                                <span className="font-medium text-sm truncate">
                                  {cat.category_name}
                                </span>
                              </div>

                              {cat.description && (
                                <p className="text-xs text-muted-foreground line-clamp-1">
                                  {cat.description}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleEditCategory(cat);
                            }}
                            title="Edit category"
                          >
                            <Edit className="w-4 h-4" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(cat.name);
                            }}
                            disabled={deletingCategory === cat.name}
                            title="Delete category"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}

            </div>

            {/* Save Button - Fixed at bottom */}
            <div className="flex justify-center pt-4 border-t">
              <Button size="lg" onClick={handleSave}>
                Save Selection
              </Button>
            </div>
          </TabsContent>

          {/* ================= CREATE TAB ================= */}
          <TabsContent value="create" className="mt-6">
            <div className="space-y-5 border rounded-lg p-4">
              {/* Name */}
              <div className="space-y-1.5">
                <Label>Category Name *</Label>
                <Input
                  placeholder="Enter category name"
                  value={newCategoryData.category_name}
                  onChange={(e) =>
                    setNewCategoryData({
                      ...newCategoryData,
                      category_name: e.target.value,
                    })
                  }
                />
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea
                  placeholder="Short description"
                  value={newCategoryData.description}
                  onChange={(e) =>
                    setNewCategoryData({
                      ...newCategoryData,
                      description: e.target.value,
                    })
                  }
                />
              </div>

              {/* Icon and Color in same row */}
              <div className="grid grid-cols-2 gap-4">
                {/* Icon */}
                <div className="space-y-1.5">
                  <Label>Icon</Label>
                  <Select
                    value={newCategoryData.icon}
                    onValueChange={(value) =>
                      setNewCategoryData({
                        ...newCategoryData,
                        icon: value,
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select an icon" />
                    </SelectTrigger>
                    <SelectContent>
                      {TABLE_ICONS.map((iconEntry) => {
                        const IconComponent = iconEntry.icon;
                        return (
                          <SelectItem key={iconEntry.name} value={iconEntry.name}>
                            <div className="flex items-center gap-2">
                              <IconComponent className="w-4 h-4" />
                              <span>{iconEntry.label}</span>
                            </div>
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>

                {/* Color */}
                <div className="space-y-1.5">
                  <Label>Color</Label>
                  <div className="flex flex-wrap items-center gap-3">
                    <Input
                      placeholder="#6366F1"
                      className="max-w-[11rem] font-mono"
                      value={newCategoryData.color}
                      onChange={(e) =>
                        setNewCategoryData({
                          ...newCategoryData,
                          color: e.target.value,
                        })
                      }
                    />
                    <input
                      type="color"
                      className="h-9 w-12 cursor-pointer rounded border bg-background p-0.5"
                      value={/^#[0-9A-Fa-f]{6}$/.test(newCategoryData.color) ? newCategoryData.color : '#6366f1'}
                      onChange={(e) =>
                        setNewCategoryData({
                          ...newCategoryData,
                          color: e.target.value,
                        })
                      }
                      aria-label="Pick category color"
                    />
                  </div>
                </div>
              </div>

              {/* Parent */}
              <div className="space-y-1.5">
                <Label>Parent Category</Label>
                <select
                  className="w-full border rounded-md p-2"
                  value={newCategoryData.parent_category}
                  onChange={(e) =>
                    setNewCategoryData({
                      ...newCategoryData,
                      parent_category: e.target.value,
                    })
                  }
                >
                  <option value="">None</option>
                  {localCategories.map((cat) => (
                    <option key={cat.name} value={cat.name}>
                      {cat.category_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Button */}
              <div className="flex gap-2 mt-2">
                <Button
                  onClick={handleCreate}
                  className="flex-1"
                  size="lg"
                  disabled={!newCategoryData.category_name.trim()}
                >
                  {editingCategory ? 'Update Category' : 'Create Category'}
                </Button>
                {editingCategory && (
                  <Button
                    type="button"
                    variant="outline"
                    size="lg"
                    onClick={() => {
                      setEditingCategory(null);
                      setNewCategoryData({
                        category_name: '',
                        description: '',
                        icon: '',
                        color: '#6366F1',
                        parent_category: '',
                      });
                    }}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}