import type { UseFormReturn } from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AdvancedSettings } from '@/components/forms/AdvancedSettings';
import type { AgentPromptFormValues } from './promptForm';

interface PromptAdvancedFieldsProps {
  form: UseFormReturn<AgentPromptFormValues>;
  /** The slug is only editable while the prompt is being created. */
  isNew: boolean;
}

/** Slug, Visibility, Description, Tags and Active, collapsed under Advanced settings. */
export function PromptAdvancedFields({ form, isNew }: PromptAdvancedFieldsProps) {
  const { errors } = form.formState;
  const hasError = Boolean(errors.slug || errors.description || errors.tags || errors.visibility);
  const setValue = (key: 'slug' | 'description' | 'tags' | 'is_active' | 'visibility', value: string | boolean) =>
    form.setValue(key, value as never, { shouldDirty: true });

  return (
    <AdvancedSettings hasError={hasError}>
      <div className="grid gap-4 sm:grid-cols-2" data-testid="prompt-advanced-fields">
        <div className="space-y-2">
          <Label htmlFor="slug">Slug</Label>
          <Input
            id="slug"
            value={form.watch('slug') || ''}
            onChange={(event) => setValue('slug', event.target.value)}
            placeholder="Auto-generated from title"
            disabled={!isNew}
          />
          <p className="text-xs text-steel-soft">
            URL-friendly identifier for this prompt template. Auto-generated from title if left blank.
          </p>
        </div>
        <div className="space-y-2">
          <Label>Visibility</Label>
          <Select
            value={form.watch('visibility')}
            onValueChange={(value) => setValue('visibility', value as AgentPromptFormValues['visibility'])}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select visibility" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Private">Private</SelectItem>
              <SelectItem value="App">App</SelectItem>
              <SelectItem value="Public">Public</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-steel-soft">Controls who can see and use this prompt template.</p>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            value={form.watch('description') || ''}
            onChange={(event) => setValue('description', event.target.value)}
            placeholder="Describe what this prompt is for"
            rows={3}
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="tags">Tags</Label>
          <Input
            id="tags"
            value={form.watch('tags') || ''}
            onChange={(event) => setValue('tags', event.target.value)}
            placeholder="Comma-separated tags"
          />
          <p className="text-xs text-steel-soft">Comma-separated tags for search and filtering.</p>
        </div>
        <div className="flex flex-row items-center justify-between rounded-md border p-4 sm:col-span-2">
          <div className="space-y-0.5">
            <Label htmlFor="is_active" className="text-base">Active</Label>
            <p className="text-xs text-steel-soft">Whether this prompt template is active and available for use.</p>
          </div>
          <Switch id="is_active" checked={form.watch('is_active')} onCheckedChange={(checked) => setValue('is_active', checked)} />
        </div>
      </div>
    </AdvancedSettings>
  );
}
