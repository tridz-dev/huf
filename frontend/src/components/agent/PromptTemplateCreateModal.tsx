import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { InstructionsTextarea } from '@/components/agent/InstructionsTextarea';
import { createAgentPrompt, type AgentPromptDoc } from '@/services/agentPromptApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const promptCreateSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  description: z.string().optional(),
  is_active: z.boolean().default(true),
  visibility: z.enum(['Public', 'App', 'Private']).default('Private'),
  tags: z.string().optional(),
  prompt_body: z.string().min(1, 'Prompt body is required'),
});

type PromptCreateFormValues = z.infer<typeof promptCreateSchema>;

const defaultValues: PromptCreateFormValues = {
  title: '',
  description: '',
  is_active: true,
  visibility: 'Private',
  tags: '',
  prompt_body: '',
};

interface PromptTemplateCreateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (prompt: AgentPromptDoc) => void;
}

/**
 * In-context "create a prompt template" dialog, used from the agent editor
 * so users don't lose their in-progress agent form (mirrors
 * KnowledgeSourceCreateModal for Knowledge sources). This only covers prompt
 * *creation* — full editing/versioning/forking still lives on the standalone
 * /prompts/:id route (AgentPromptFormPage), which is deeply tied to
 * page-level routing and version state and isn't a good fit for extraction
 * into a shared modal-friendly form.
 */
export function PromptTemplateCreateModal({ open, onOpenChange, onCreated }: PromptTemplateCreateModalProps) {
  const [saving, setSaving] = useState(false);

  const form = useForm<PromptCreateFormValues>({
    resolver: zodResolver(promptCreateSchema),
    defaultValues,
  });

  useEffect(() => {
    if (!open) return;
    form.reset(defaultValues);
  }, [open, form]);

  const handleOpenChange = (next: boolean) => {
    if (!next && form.formState.isDirty) {
      const confirmed = window.confirm('Discard this prompt template? Your changes will be lost.');
      if (!confirmed) return;
    }
    onOpenChange(next);
  };

  const onSubmit = async (values: PromptCreateFormValues) => {
    setSaving(true);
    try {
      const created = await createAgentPrompt({
        title: values.title,
        description: values.description || undefined,
        is_active: values.is_active ? 1 : 0,
        visibility: values.visibility,
        tags: values.tags || undefined,
        prompt_body: values.prompt_body,
      });
      toast.success('Prompt template created');
      onCreated(created);
      onOpenChange(false);
    } catch (error) {
      console.error('Error creating prompt template:', error);
      const msg = getFrappeErrorMessage(error);
      toast.error(msg || 'Failed to create prompt template');
    } finally {
      setSaving(false);
    }
  };

  const handleFormSubmit = form.handleSubmit(onSubmit, () => {
    toast.error('Please fix the highlighted fields');
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogScrollContent className="sm:max-w-2xl">
        <DialogScrollHeader>
          <DialogTitle>New Prompt Template</DialogTitle>
          <DialogDescription>
            Create a reusable prompt template your agents can link to.
          </DialogDescription>
        </DialogScrollHeader>

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <DialogScrollBody className="space-y-4 pb-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="Prompt title" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="visibility"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Visibility</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select visibility" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="Private">Private</SelectItem>
                          <SelectItem value="App">App</SelectItem>
                          <SelectItem value="Public">Public</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="tags"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tags</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="Comma-separated tags" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder="Describe what this prompt is for" rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="prompt_body"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Prompt Body</FormLabel>
                    <FormControl>
                      <InstructionsTextarea
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Write the prompt instructions here"
                        className="min-h-[220px] font-mono resize-y"
                        showOptimize={false}
                        showExpand
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
                    <div className="space-y-0.5 pr-4">
                      <FormLabel className="text-base">Active</FormLabel>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </DialogScrollBody>

            <DialogScrollFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Creating...' : 'Create'}
              </Button>
            </DialogScrollFooter>
          </form>
        </Form>
      </DialogScrollContent>
    </Dialog>
  );
}
