import { useState } from 'react';
import { Brain, Settings, Database, Search, Plus, Trash2, Edit, Info } from 'lucide-react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { UseFormReturn } from 'react-hook-form';
import type { MemoryPolicy, MemoryProfile } from '@/types/memory.types';
import type { AgentFormValues } from './types';

interface MemoryTabProps {
  form: UseFormReturn<AgentFormValues>;
  memoryPolicies: MemoryPolicy[];
  memoryProfiles: MemoryProfile[];
  onCreatePolicy: () => void;
  onEditPolicy: (policyName: string) => void;
  onDeletePolicy: (policyName: string) => void;
}

export function MemoryTab({
  form,
  memoryPolicies,
  memoryProfiles,
  onCreatePolicy,
  onEditPolicy,
  onDeletePolicy,
}: MemoryTabProps) {
  const [activeSubTab, setActiveSubTab] = useState('settings');
  const enableMemory = form.watch('enable_memory');
  const selectedPolicy = form.watch('memory_policy');
  const selectedProfile = form.watch('memory_profile');

  // Get policy details if selected
  const policyDetails = selectedPolicy 
    ? memoryPolicies.find(p => p.name === selectedPolicy)
    : null;

  // Get profile details if selected
  const profileDetails = selectedProfile
    ? memoryProfiles.find(p => p.name === selectedProfile)
    : null;

  return (
    <div className="space-y-6">
      {/* Enable Memory Toggle */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Brain className="w-5 h-5 text-primary" />
              </div>
              <div>
                <CardTitle>Memory System</CardTitle>
                <CardDescription>Enable memory capabilities for this agent</CardDescription>
              </div>
            </div>
            <FormField
              control={form.control}
              name="enable_memory"
              render={({ field }) => (
                <FormItem className="flex items-center space-x-2 space-y-0">
                  <FormControl>
                    <Switch 
                      checked={field.value} 
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
          </div>
        </CardHeader>
        {enableMemory && (
          <CardContent className="pt-0">
            <p className="text-sm text-muted-foreground">
              When enabled, this agent can capture, store, and retrieve memories from conversations. 
              Configure memory policies and settings below.
            </p>
          </CardContent>
        )}
      </Card>

      {enableMemory && (
        <Tabs value={activeSubTab} onValueChange={setActiveSubTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="settings">
              <Settings className="w-4 h-4 mr-2" />
              Settings
            </TabsTrigger>
            <TabsTrigger value="policy">
              <Database className="w-4 h-4 mr-2" />
              Policy
            </TabsTrigger>
            <TabsTrigger value="retrieval">
              <Search className="w-4 h-4 mr-2" />
              Retrieval
            </TabsTrigger>
          </TabsList>

          {/* Settings Tab */}
          <TabsContent value="settings" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Memory Configuration</CardTitle>
                <CardDescription>Basic memory settings for this agent</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-6">
                {/* Memory Policy Selection */}
                <FormField
                  control={form.control}
                  name="memory_policy"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="flex items-center gap-2">
                        Memory Policy
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs">
                                A memory policy defines when and how memories are captured. 
                                Select an existing policy or create a new one.
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </FormLabel>
                      <div className="flex gap-2">
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger className="flex-1">
                              <SelectValue placeholder="Select a memory policy" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="">None (use defaults)</SelectItem>
                            {memoryPolicies.map((policy) => (
                              <SelectItem key={policy.name} value={policy.name}>
                                {policy.policy_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button type="button" variant="outline" size="icon" onClick={onCreatePolicy}>
                          <Plus className="w-4 h-4" />
                        </Button>
                        {field.value && (
                          <>
                            <Button 
                              type="button" 
                              variant="outline" 
                              size="icon"
                              onClick={() => onEditPolicy(field.value)}
                            >
                              <Edit className="w-4 h-4" />
                            </Button>
                            <Button 
                              type="button" 
                              variant="outline" 
                              size="icon"
                              onClick={() => onDeletePolicy(field.value)}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </>
                        )}
                      </div>
                      {policyDetails && (
                        <div className="mt-2 p-3 bg-muted/50 rounded-md text-sm">
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant={policyDetails.enabled ? "default" : "secondary"}>
                              {policyDetails.enabled ? "Enabled" : "Disabled"}
                            </Badge>
                            <span className="text-muted-foreground">
                              Stage: {policyDetails.capture_stage}
                            </span>
                          </div>
                          <p className="text-muted-foreground">
                            Owner: {policyDetails.capture_owner} • Frequency: {policyDetails.capture_frequency_type}
                          </p>
                        </div>
                      )}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Memory Profile Selection */}
                <FormField
                  control={form.control}
                  name="memory_profile"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="flex items-center gap-2">
                        Memory Profile
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs">
                                A memory profile defines the schema and capture behavior 
                                for specific types of memories (e.g., programming, travel, science).
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a memory profile" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="">Default (no schema)</SelectItem>
                          {memoryProfiles.map((profile) => (
                            <SelectItem key={profile.name} value={profile.name}>
                              {profile.icon && <span className="mr-2">{profile.icon}</span>}
                              {profile.profile_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {profileDetails && (
                        <div className="mt-2 p-3 bg-muted/50 rounded-md">
                          <div className="flex items-center gap-2 mb-1">
                            {profileDetails.icon && <span className="text-lg">{profileDetails.icon}</span>}
                            <Badge variant="outline">{profileDetails.category}</Badge>
                            {profileDetails.is_system_profile && (
                              <Badge variant="secondary">System</Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {profileDetails.description}
                          </p>
                        </div>
                      )}
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
                      <FormLabel className="flex items-center gap-2">
                        Memory Agent
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs">
                                Optional dedicated agent for memory capture. 
                                If not specified, the main agent handles memory operations.
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="Agent name for memory capture" 
                          {...field} 
                        />
                      </FormControl>
                      <FormDescription>
                        Dedicated agent to handle memory capture (optional)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Memory Run Order */}
                <FormField
                  control={form.control}
                  name="memory_run_order"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Memory Run Order</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="before_main_response">
                            Before Main Response
                          </SelectItem>
                          <SelectItem value="after_main_response">
                            After Main Response
                          </SelectItem>
                          <SelectItem value="background">
                            Background (Async)
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        When memory operations execute relative to the main agent response
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Scope Type */}
                <FormField
                  control={form.control}
                  name="default_memory_scope_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Default Memory Scope</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="conversation">Conversation (isolated)</SelectItem>
                          <SelectItem value="user">User (cross-conversation)</SelectItem>
                          <SelectItem value="agent">Agent (global for this agent)</SelectItem>
                          <SelectItem value="namespace">Namespace (shared scope)</SelectItem>
                          <SelectItem value="global">Global (all agents)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Default scope for new memories created by this agent
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
                      <FormLabel>Scope Key Template</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="e.g., {{user}}-{{namespace}}" 
                          {...field} 
                        />
                      </FormControl>
                      <FormDescription>
                        Template for generating scope keys (supports {'{{user}}'}, {'{{agent}}'}, {'{{namespace}}'})
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            {/* Memory Tools */}
            <Card>
              <CardHeader>
                <CardTitle>Memory Tools</CardTitle>
                <CardDescription>Enable tools for memory operations</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="enable_memory_search_tool"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <FormLabel className="text-base">Memory Search Tool</FormLabel>
                        <FormDescription>
                          Allow agent to search and retrieve memories during conversations
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
                        <FormLabel className="text-base">Memory Write Tool</FormLabel>
                        <FormDescription>
                          Allow agent to explicitly create and update memories
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
          </TabsContent>

          {/* Policy Tab */}
          <TabsContent value="policy" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Indexing Configuration</CardTitle>
                <CardDescription>How memories are indexed for search</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <FormField
                  control={form.control}
                  name="memory_index_backend_default"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Default Index Backend</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="none">None (no indexing)</SelectItem>
                          <SelectItem value="sqlite_fts">SQLite FTS (full-text search)</SelectItem>
                          <SelectItem value="sqlite_vec">SQLite + Vector (hybrid)</SelectItem>
                          <SelectItem value="pgvector">PgVector (PostgreSQL)</SelectItem>
                          <SelectItem value="custom">Custom</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Backend for indexing memories. Hybrid (FTS + Vector) recommended.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="memory_visibility_default"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Default Visibility</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="private">Private (owner only)</SelectItem>
                          <SelectItem value="shared_with_agent">Shared with Agent</SelectItem>
                          <SelectItem value="shared_with_namespace">Shared with Namespace</SelectItem>
                          <SelectItem value="global">Global (all agents)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Who can see memories created by this agent
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Retrieval Tab */}
          <TabsContent value="retrieval" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Retrieval Settings</CardTitle>
                <CardDescription>How memories are retrieved and injected</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <FormField
                  control={form.control}
                  name="memory_retrieval_mode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Retrieval Mode</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="inject">
                            Inject (automatically include in prompt)
                          </SelectItem>
                          <SelectItem value="tool_only">
                            Tool Only (agent must request memories)
                          </SelectItem>
                          <SelectItem value="hybrid">
                            Hybrid (inject + allow tool access)
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        How memories are made available to the agent
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="memory_max_items"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Max Items to Inject: {field.value || 5}</FormLabel>
                      <FormControl>
                        <Slider 
                          min={1} 
                          max={20} 
                          step={1} 
                          value={[field.value || 5]} 
                          onValueChange={(vals) => field.onChange(vals[0])} 
                        />
                      </FormControl>
                      <FormDescription>
                        Maximum number of memories to inject into prompts
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="memory_in_prompt_budget"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Prompt Token Budget: {field.value || 1000} tokens</FormLabel>
                      <FormControl>
                        <Slider 
                          min={100} 
                          max={4000} 
                          step={100} 
                          value={[field.value || 1000]} 
                          onValueChange={(vals) => field.onChange(vals[0])} 
                        />
                      </FormControl>
                      <FormDescription>
                        Maximum tokens to use for memory content in prompts
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
