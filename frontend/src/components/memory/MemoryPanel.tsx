import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import { Brain, Database, Search, Share2, Shield, Sparkles, Wrench } from 'lucide-react';
import { UseFormReturn } from 'react-hook-form';
import type { MemoryFormValues, MemoryScopeType, MemoryRetrievalMode, MemoryIndexBackend } from '@/types/memory.types';
import { useMemoryPolicies } from './hooks/useMemory';
import { useMemoryProfiles } from './hooks/useMemory';

interface MemoryPanelProps {
  form: UseFormReturn<MemoryFormValues>;
}

const scopeTypeLabels: Record<MemoryScopeType, { label: string; description: string; icon: React.ReactNode }> = {
  conversation: {
    label: 'Conversation',
    description: 'Memory visible only inside the current conversation',
    icon: <Sparkles className="w-4 h-4" />,
  },
  user: {
    label: 'User',
    description: 'Memory visible across all sessions for the same user',
    icon: <Shield className="w-4 h-4" />,
  },
  agent: {
    label: 'Agent',
    description: 'Memory shared across all users of this agent',
    icon: <Brain className="w-4 h-4" />,
  },
  namespace: {
    label: 'Namespace',
    description: 'Custom scope shared by a chosen group',
    icon: <Share2 className="w-4 h-4" />,
  },
  global: {
    label: 'Global',
    description: 'Visible to all eligible agents',
    icon: <Database className="w-4 h-4" />,
  },
};

const retrievalModeLabels: Record<MemoryRetrievalMode, { label: string; description: string }> = {
  inject: {
    label: 'Auto-inject',
    description: 'Automatically inject relevant memories into prompts',
  },
  tool_only: {
    label: 'Tool Search',
    description: 'Agent must explicitly query memory via tool',
  },
  hybrid: {
    label: 'Hybrid',
    description: 'Top memories are injected, rest remains searchable',
  },
};

const indexBackendLabels: Record<MemoryIndexBackend, string> = {
  none: 'No Index',
  sqlite_fts: 'SQLite FTS',
  sqlite_vec: 'SQLite Vector',
  pgvector: 'PostgreSQL Vector',
  custom: 'Custom Backend',
};

export function MemoryPanel({ form }: MemoryPanelProps) {
  const enableMemory = form.watch('enable_memory');
  const retrievalMode = form.watch('memory_retrieval_mode');
  const scopeType = form.watch('default_memory_scope_type');
  const maxItems = form.watch('memory_max_items') || 10;

  const { policies, loading: loadingPolicies } = useMemoryPolicies();
  const { profiles, loading: loadingProfiles } = useMemoryProfiles();

  return (
    <div className="space-y-6">
      {/* Enable Memory Toggle */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-indigo-500" />
            <CardTitle>Agent Memory</CardTitle>
          </div>          
          <CardDescription>
            Enable this agent to capture, store, and retrieve structured memory across conversations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FormField
            control={form.control}
            name="enable_memory"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Memory</FormLabel>
                  <FormDescription>
                    Allow this agent to maintain durable, scoped memory records.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      {enableMemory && (
        <>
          {/* Memory Configuration */}
          <Card>
            <CardHeader>
              <CardTitle>Memory Configuration</CardTitle>
              <CardDescription>
                Configure how this agent captures and stores memories.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Memory Policy */}
              <FormField
                control={form.control}
                name="memory_policy"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Memory Policy</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || ''}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a memory policy" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="">Default (none)</SelectItem>
                        {loadingPolicies ? (
                          <SelectItem value="loading" disabled>Loading policies...</SelectItem>
                        ) : (
                          policies.map((policy) => (
                            <SelectItem key={policy.name} value={policy.name}>
                              {policy.policy_name}
                              {!policy.enabled && (
                                <Badge variant="secondary" className="ml-2 text-xs">Disabled</Badge>
                              )}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Choose a policy to control capture timing, frequency, and triggers.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Memory Profile */}
              <FormField
                control={form.control}
                name="memory_profile"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Memory Profile</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || ''}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a memory profile" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="">Custom (no profile)</SelectItem>
                        {loadingProfiles ? (
                          <SelectItem value="loading" disabled>Loading profiles...</SelectItem>
                        ) : (
                          profiles.map((profile) => (
                            <SelectItem key={profile.name} value={profile.name}>
                              {profile.profile_name}
                              {profile.is_system_profile && (
                                <Badge variant="outline" className="ml-2 text-xs">System</Badge>
                              )}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Profiles provide opinionated schemas and capture prompts for common domains.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Memory Agent */}
              <FormField
                control={form.control}
                name="memory_agent"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Memory Agent (Optional)</FormLabel>
                    <FormControl>
                      <input
                        type="text"
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        placeholder="Agent name for specialized memory extraction"
                        {...field}
                        value={field.value || ''}
                      />
                    </FormControl>
                    <FormDescription>
                      Optional dedicated agent for memory extraction with different model/settings.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Scope & Sharing */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Share2 className="w-5 h-5 text-emerald-500" />
                <CardTitle>Scope & Sharing</CardTitle>
              </div>
              <CardDescription>
                Control where memories are stored and who can access them.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Default Scope Type */}
              <FormField
                control={form.control}
                name="default_memory_scope_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default Scope</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select scope type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {(Object.keys(scopeTypeLabels) as MemoryScopeType[]).map((scope) => (
                          <SelectItem key={scope} value={scope}>
                            <div className="flex items-center gap-2">
                              {scopeTypeLabels[scope].icon}
                              <span>{scopeTypeLabels[scope].label}</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {scopeTypeLabels[scopeType]?.description}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Scope Key Template */}
              <FormField
                control={form.control}
                name="default_memory_scope_key_template"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Scope Key Template (Optional)</FormLabel>
                    <FormControl>
                      <input
                        type="text"
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        placeholder="e.g., {{{user}}}_{{{project}}}"
                        {...field}
                        value={field.value || ''}
                      />
                    </FormControl>
                    <FormDescription>
                      Template for generating scope keys. Supports variables like {'{{user}}'}, {'{{agent}}'}.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Visibility */}
              <FormField
                control={form.control}
                name="memory_visibility_default"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default Visibility</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select visibility" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="private">Private</SelectItem>
                        <SelectItem value="shared_with_agent">Shared with Agent</SelectItem>
                        <SelectItem value="shared_with_namespace">Shared with Namespace</SelectItem>
                        <SelectItem value="global">Global</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Control who can see memories created by this agent.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Retrieval Settings */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Search className="w-5 h-5 text-amber-500" />
                <CardTitle>Retrieval</CardTitle>
              </div>
              <CardDescription>
                Configure how memories are retrieved and used during conversations.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Retrieval Mode */}
              <FormField
                control={form.control}
                name="memory_retrieval_mode"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Retrieval Mode</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select retrieval mode" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {(Object.keys(retrievalModeLabels) as MemoryRetrievalMode[]).map((mode) => (
                          <SelectItem key={mode} value={mode}>
                            {retrievalModeLabels[mode].label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {retrievalModeLabels[retrievalMode]?.description}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Max Items to Inject */}
              {retrievalMode !== 'tool_only' && (
                <FormField
                  control={form.control}
                  name="memory_max_items"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Max Items to Inject: {field.value || 10}</FormLabel>
                      <FormControl>
                        <Slider
                          min={1}
                          max={50}
                          step={1}
                          value={[field.value || 10]}
                          onValueChange={(vals) => field.onChange(vals[0])}
                        />
                      </FormControl>
                      <FormDescription>
                        Maximum number of memory items to inject into prompts (when using auto-inject or hybrid mode).
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {/* Prompt Budget */}
              <FormField
                control={form.control}
                name="memory_in_prompt_budget"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Prompt Budget (tokens)</FormLabel>
                    <FormControl>
                      <input
                        type="number"
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        placeholder="2000"
                        min={0}
                        {...field}
                        value={field.value || ''}
                        onChange={(e) => field.onChange(e.target.value ? parseInt(e.target.value, 10) : undefined)}
                      />
                    </FormControl>
                    <FormDescription>
                      Maximum tokens allocated for memory context in prompts.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Index Backend */}
              <FormField
                control={form.control}
                name="memory_index_backend_default"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default Index Backend</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select index backend" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {(Object.keys(indexBackendLabels) as MemoryIndexBackend[]).map((backend) => (
                          <SelectItem key={backend} value={backend}>
                            {indexBackendLabels[backend]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Storage backend for indexing and searching memories.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Tools */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Wrench className="w-5 h-5 text-purple-500" />
                <CardTitle>Memory Tools</CardTitle>
              </div>
              <CardDescription>
                Enable additional tools for memory operations.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="enable_memory_search_tool"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Search Tool</FormLabel>
                      <FormDescription>
                        Allow the agent to explicitly search memory records.
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="enable_memory_write_tool"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Write Tool</FormLabel>
                      <FormDescription>
                        Allow the agent to manually create and update memory records.
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="memory_run_order"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Memory Agent Run Order</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select run order" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="before_main_response">Before Main Response</SelectItem>
                        <SelectItem value="after_main_response">After Main Response</SelectItem>
                        <SelectItem value="background">Background (Async)</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      When to run the memory agent relative to the main agent response.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
