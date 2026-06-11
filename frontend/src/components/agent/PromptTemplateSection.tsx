import { Badge } from '@/components/ui/badge';
import { Combobox } from '@/components/ui/combobox';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import type { AgentFormValues } from './types';
import type { UseFormReturn } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { Plus } from 'lucide-react';

export interface AgentPromptOption {
  value: string;
  label: string;
  description?: string;
  version?: number | null;
  isLatest?: boolean;
}

interface PromptTemplateSectionProps {
  form: UseFormReturn<AgentFormValues>;
  promptOptions: AgentPromptOption[];
  loadingPrompts?: boolean;
  showAddNew?: boolean;
}

export function PromptTemplateSection({
  form,
  promptOptions,
  loadingPrompts = false,
  showAddNew = true,
}: PromptTemplateSectionProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const selectedPrompt = promptOptions.find((option) => option.value === form.watch('agent_prompt'));
  const attachedVersion = form.watch('template_version_at_attach');
  const isLocked = form.watch('prompt_version_locked');
  const promptComboboxOptions = promptOptions.map((option) => ({
    ...option,
    subtitle: option.version ? `Version ${option.version}` : undefined,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prompt Template</CardTitle>
        <CardDescription>
          Reuse a managed Agent Prompt template instead of local instructions. Version locking keeps the
          agent pinned to the attached template revision.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 sm:grid-cols-2">
        <FormField
          control={form.control}
          name="agent_prompt"
          render={({ field }) => (
            <FormItem id="agent-prompt-field" className="sm:col-span-2">
              <FormLabel>Agent Prompt</FormLabel>
              <div className="flex items-center gap-2">
                <FormControl>
                  <Combobox
                    options={promptComboboxOptions}
                    value={field.value}
                    onValueChange={field.onChange}
                    placeholder={loadingPrompts ? 'Loading templates...' : 'Select an Agent Prompt'}
                    disabled={loadingPrompts}
                    searchPlaceholder="Search templates..."
                    emptyText="No active prompt templates found."
                  />
                </FormControl>
                {showAddNew ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      (() => {
                        const returnTo = `${location.pathname}#general`;
                        const selectedPromptField = 'agent_prompt';
                        // Fallback for cases where react-router location.state is lost.
                        try {
                          localStorage.setItem(
                            'agentPromptCreateReturnTo',
                            JSON.stringify({ returnTo, selectedPromptField })
                          );
                        } catch {
                          // ignore storage failures
                        }
                        navigate('/prompts/new', {
                          state: {
                            returnTo,
                            selectedPromptField,
                          },
                        });
                      })()
                    }
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    New
                  </Button>
                ) : null}
              </div>
              <FormDescription>
                Pick an active prompt from the shared template library. The backend records the current
                version when you attach it.
              </FormDescription>
              {selectedPrompt && (
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  {selectedPrompt.version ? (
                    <Badge variant="outline">Current template v{selectedPrompt.version}</Badge>
                  ) : null}
                  {selectedPrompt.isLatest ? <Badge variant="secondary">Latest</Badge> : null}
                  {selectedPrompt.description ? (
                    <span className="text-sm text-muted-foreground">{selectedPrompt.description}</span>
                  ) : null}
                </div>
              )}
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="prompt_version_locked"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
              <div className="space-y-0.5 pr-4">
                <FormLabel className="text-base">Lock Template Version</FormLabel>
                <FormDescription>
                  Keep this agent pinned to the attached version instead of following the latest template
                  updates automatically.
                </FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="template_version_at_attach"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Attached at Version</FormLabel>
              <FormControl>
                <div className="flex min-h-10 items-center rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground">
                  {field.value ?? 'Will be recorded after template attachment'}
                </div>
              </FormControl>
              <FormDescription>
                {isLocked && attachedVersion
                  ? `This agent is locked to version ${attachedVersion}.`
                  : 'Read-only snapshot captured by the backend when a template is attached or changed.'}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
