import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Plus, Tag, Trash2, Pencil, Check } from 'lucide-react';
import { toast } from 'sonner';
import {
  createCategory,
  deleteCategory,
  getSummaryPromptCategories,
  updateCategory,
  type CategoryDoc,
} from '@/services/categoryApi';

interface SummaryPromptCategoriesModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategoryName: string | null;
  onSelectCategory: (category: CategoryDoc | null) => void;
  editCategory?: CategoryDoc | null;
  onEditComplete?: () => void;
}

const EMPTY_FORM = {
  category_name: '',
  description: '',
  color: '#6366F1',
  parent_category: '',
};

export function SummaryPromptCategoriesModal({
  open,
  onOpenChange,
  selectedCategoryName,
  onSelectCategory,
  editCategory,
  onEditComplete,
}: SummaryPromptCategoriesModalProps) {
  const [categories, setCategories] = useState<CategoryDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [formData, setFormData] = useState(EMPTY_FORM);
  const [editingName, setEditingName] = useState<string | null>(null);

  const parentOptions = useMemo(
    () =>
      categories
        .filter((category) => category.name !== editingName)
        .map((category) => ({
          value: category.name,
          label: category.category_name || category.name,
        })),
    [categories, editingName],
  );

  const loadCategories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSummaryPromptCategories();
      setCategories(data);
    } catch {
      toast.error('Failed to load summary prompt categories');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadCategories();
    }
  }, [open, loadCategories]);

  useEffect(() => {
    if (!open) return;

    if (editCategory) {
      setEditingName(editCategory.name);
      setShowCreate(true);
      setFormData({
        category_name: editCategory.category_name,
        description: editCategory.description || '',
        color: editCategory.color || '#6366F1',
        parent_category: editCategory.parent_category || '',
      });
      return;
    }

    setEditingName(null);
    setFormData(EMPTY_FORM);
    setShowCreate(false);
  }, [open, editCategory]);

  const resetForm = () => {
    setFormData(EMPTY_FORM);
    setEditingName(null);
    setShowCreate(false);
    onEditComplete?.();
  };

  const handleSave = async () => {
    if (!formData.category_name.trim()) {
      toast.error('Category name is required');
      return;
    }

    setSaving(true);
    try {
      const payload: Partial<CategoryDoc> = {
        category_name: formData.category_name.trim(),
        description: formData.description.trim() || undefined,
        color: formData.color || undefined,
        parent_category: formData.parent_category || undefined,
      };

      if (editingName) {
        const updated = await updateCategory(editingName, payload, 'summary');
        toast.success('Category updated');
        if (selectedCategoryName === editingName) {
          onSelectCategory(updated);
        }
      } else {
        const created = await createCategory(payload, 'summary');
        toast.success('Category created');
        onSelectCategory(created);
      }

      resetForm();
      await loadCategories();
    } catch {
      toast.error(editingName ? 'Failed to update category' : 'Failed to create category');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (name: string) => {
    setDeletingName(name);
    try {
      await deleteCategory(name, 'summary');
      toast.success('Category deleted');
      if (selectedCategoryName === name) {
        onSelectCategory(null);
      }
      if (editingName === name) {
        resetForm();
      }
      await loadCategories();
    } catch {
      toast.error('Failed to delete category');
    } finally {
      setDeletingName(null);
    }
  };

  const handleSelect = (category: CategoryDoc) => {
    onSelectCategory(category);
    onOpenChange(false);
  };

  const startEdit = (category: CategoryDoc) => {
    setEditingName(category.name);
    setShowCreate(true);
    setFormData({
      category_name: category.category_name,
      description: category.description || '',
      color: category.color || '#6366F1',
      parent_category: category.parent_category || '',
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle>Summary Prompt Categories</DialogTitle>
          <DialogDescription>
            Browse, create, and assign categories for agent summary prompts
          </DialogDescription>
        </DialogScrollHeader>

        <DialogScrollBody className="space-y-4 py-2">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {categories.length} {categories.length === 1 ? 'category' : 'categories'}
            </p>
            <Button
              size="sm"
              variant={showCreate ? 'secondary' : 'default'}
              onClick={() => {
                if (showCreate) {
                  resetForm();
                } else {
                  setShowCreate(true);
                  setEditingName(null);
                  setFormData(EMPTY_FORM);
                }
              }}
            >
              <Plus className="w-4 h-4 mr-2" />
              New Category
            </Button>
          </div>

          {showCreate && (
            <div className="rounded-lg border p-4 space-y-4">
              <p className="text-sm font-medium">
                {editingName ? 'Edit Category' : 'New Category'}
              </p>

              <div className="space-y-2">
                <Label>Category Name</Label>
                <Input
                  placeholder="e.g. Summarization"
                  value={formData.category_name}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, category_name: e.target.value }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>Description</Label>
                <Textarea
                  placeholder="Optional description"
                  className="min-h-[80px] resize-y"
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Color</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="color"
                      value={formData.color}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, color: e.target.value }))
                      }
                      className="h-10 w-14 p-1"
                    />
                    <Input
                      value={formData.color}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, color: e.target.value }))
                      }
                      placeholder="#6366F1"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Parent Category</Label>
                  <Select
                    value={formData.parent_category || '__none__'}
                    onValueChange={(value) =>
                      setFormData((prev) => ({
                        ...prev,
                        parent_category: value === '__none__' ? '' : value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {parentOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={resetForm}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  {editingName ? 'Update' : 'Create'}
                </Button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : categories.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No categories yet. Create one to get started.
            </div>
          ) : (
            <div className="space-y-2">
              {categories.map((category) => {
                const isSelected = selectedCategoryName === category.name;
                return (
                  <div
                    key={category.name}
                    className={`flex items-center gap-3 rounded-lg border p-3 ${
                      isSelected ? 'border-primary bg-primary/5' : ''
                    }`}
                  >
                    <Tag
                      className="w-4 h-4 flex-shrink-0"
                      style={{ color: category.color || '#6366F1' }}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {category.category_name}
                      </p>
                      {category.description ? (
                        <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                          {category.description}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        variant={isSelected ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => handleSelect(category)}
                        title="Use this category"
                      >
                        <Check className="w-3.5 h-3.5 mr-1" />
                        {isSelected ? 'Selected' : 'Select'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => startEdit(category)}
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleDelete(category.name)}
                        title="Delete"
                        className="text-destructive hover:text-destructive"
                        disabled={deletingName === category.name}
                      >
                        {deletingName === category.name ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </DialogScrollBody>
      </DialogScrollContent>
    </Dialog>
  );
}
