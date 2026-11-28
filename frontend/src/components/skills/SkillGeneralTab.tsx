import type { UseFormReturn } from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { CategoryTab } from '@/components/category/CategoryTab';
import { AdvancedSettings } from '@/components/forms/AdvancedSettings';
import { SKILL_ADVANCED_FIELDS, type SkillFormValues } from '@/components/skills/skillFormSchema';
import type { CategoryDoc } from '@/services/categoryApi';


type TextKey = Exclude<keyof SkillFormValues, 'auto_load'>;
type AnyForm = UseFormReturn<SkillFormValues>;

interface SkillGeneralTabProps {
  form: AnyForm;
  selectedCategory: CategoryDoc | null;
  onAddCategory: () => void;
  onRemoveCategory: () => void;
  onEditCategory: (category: CategoryDoc) => void;
}

function TextField({
  form,
  name,
  label,
  placeholder,
  help,
}: {
  form: AnyForm;
  name: TextKey;
  label: string;
  placeholder?: string;
  help?: string;
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input placeholder={placeholder} {...field} />
          </FormControl>
          {help && <FormDescription>{help}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function SelectField({
  form,
  name,
  label,
  options,
}: {
  form: AnyForm;
  name: TextKey;
  label: string;
  options: string[];
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <SelectTrigger>
                <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o} value={o}>
                  {o}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

export function SkillGeneralTab({
  form,
  selectedCategory,
  onAddCategory,
  onRemoveCategory,
  onEditCategory,
}: SkillGeneralTabProps) {
  const errors = form.formState.errors;
  const advancedHasError = SKILL_ADVANCED_FIELDS.some((f) => !!errors[f]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>General</CardTitle>
        <CardDescription>Basic skill configuration</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <TextField form={form} name="title" label="Title" placeholder="e.g. Email parser" />
        <CategoryTab
          itemLabel="skill"
          selectedCategory={selectedCategory}
          onAddCategory={onAddCategory}
          onRemoveCategory={onRemoveCategory}
          onEditCategory={onEditCategory}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Short description shown in the UI and to agents"
                  className="min-h-[80px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="instructions"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Instructions</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="System prompt text injected when this skill is loaded"
                  className="min-h-[160px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <AdvancedSettings hasError={advancedHasError} className="sm:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField form={form} name="status" label="Status" options={['Draft', 'Active', 'Error', 'Disabled']} />
            <TextField form={form} name="version" label="Version" placeholder="1.0.0" />
            <TextField form={form} name="author" label="Author" placeholder="Author or organization" />
            <SelectField
              form={form}
              name="source_type"
              label="Source type"
              options={['Local', 'Git', 'Common Destination', 'App Provided']}
            />
            <TextField
              form={form}
              name="provider_app"
              label="Provider app"
              placeholder="huf"
              help="Required for App Provided skills"
            />
            <TextField
              form={form}
              name="source_url"
              label="Source URL"
              placeholder="https://github.com/org/repo"
              help="Records where this skill came from (provenance). It is not fetched or synced."
            />
            <TextField form={form} name="source_path" label="Source path" placeholder="skills" />
            <TextField form={form} name="source_ref" label="Source ref" placeholder="main" />
            <FormField
              control={form.control}
              name="auto_load"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Auto load</FormLabel>
                    <FormDescription>Load this skill automatically when attached</FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          </div>
        </AdvancedSettings>
      </CardContent>
    </Card>
  );
}
