import { useState } from 'react';
import { Brain, Settings, Database, Search, Plus, Trash2, Edit, Info, HelpCircle } from 'lucide-react';
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

// Help text definitions for consistent documentation
const HELP_TEXT = {
  enableMemory: "When enabled, this agent can capture, store, and retrieve memories from conversations. Memories persist across sessions and provide context continuity.",
  memoryPolicy: "A memory policy defines when and how memories are captured. It controls capture frequency, quality thresholds, and storage behavior. Select an existing policy or create a custom one.",
  memoryProfile: "A memory profile defines the schema and capture behavior for specific types of memories. Choose a profile that matches your agent's domain (e.g., Programming, CRM, Travel).",
  memoryAgent: "A dedicated agent specifically for memory capture. Using a separate agent can improve capture quality but adds overhead. Leave empty to use the main agent for capture.",
  memoryRunOrder: "Determines when memory operations execute relative to the main agent response. 'Before' = memories available during generation. 'After' = memories from current turn. 'Background' = non-blocking.",
  memoryScope: "Controls how widely memories are shared. 'Conversation' = isolated to this chat. 'User' = shared across user's conversations. 'Agent' = global for this agent. 'Namespace' = shared group. 'Global' = all agents.",
  scopeKeyTemplate: "Template for generating unique scope identifiers. Variables: {{user}} = user ID, {{agent}} = agent name, {{namespace}} = namespace. Example: '{{user}}-support' creates per-user support memories.",
  memorySearchTool: "Allows the agent to actively search its memory during conversations. The agent decides when to search based on context.",
  memoryWriteTool: "Allows the agent to explicitly create and update memories. Useful for user-driven memory management.",
  indexBackend: "How memories are indexed for search. 'FTS' = keyword search. 'Vector' = semantic similarity. 'Hybrid' = both. 'None' = retrieval by ID only.",
  memoryVisibility: "Who can see memories created by this agent. 'Private' = owner only. 'Agent' = owner + this agent. 'Namespace' = group members. 'Global' = everyone.",
  retrievalMode: "How memories are provided to the agent. 'Inject' = auto-included in prompts. 'Tool Only' = agent must request. 'Hybrid' = both methods.",
  maxItemsToInject: "Maximum memories to include in a single prompt. Prevents context overflow. More items = more context but higher token usage.",
  tokenBudget: "Maximum tokens to allocate for memory content in prompts. Acts as a safety limit to prevent exceeding the model's context window.",
};

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
    <TooltipProvider delayDuration={100}>
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
                  <CardTitle className="flex items-center gap-2">
                    Memory System
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        <p>{HELP_TEXT.enableMemory}</p>
                      </TooltipContent>
                    </Tooltip>
                  </CardTitle>
                  <CardDescription>Enable persistent memory capabilities</CardDescription>
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
                Memory is enabled. Configure policies, profiles, and retrieval settings below to customize behavior.
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
                Storage
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
                  <CardTitle className="flex items-center gap-2">
                    Memory Configuration
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        <p>Core settings that control how this agent uses memory.</p>
                      </TooltipContent>
                    </Tooltip>
                  </CardTitle>
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryPolicy}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <div className="flex gap-2">
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger className="flex-1">
                                <SelectValue placeholder="Select a memory policy" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="">
                                <span className="text-muted-foreground">None (use defaults)</span>
                              </SelectItem>
                              {memoryPolicies.map((policy) => (
                                <SelectItem key={policy.name} value={policy.name}>
                                  {policy.policy_name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button type="button" variant="outline" size="icon" onClick={onCreatePolicy}>
                                <Plus className="w-4 h-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Create new policy</TooltipContent>
                          </Tooltip>
                          {field.value && (
                            <>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button 
                                    type="button" 
                                    variant="outline" 
                                    size="icon"
                                    onClick={() => onEditPolicy(field.value)}
                                  >
                                    <Edit className="w-4 h-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Edit policy</TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button 
                                    type="button" 
                                    variant="outline" 
                                    size="icon"
                                    onClick={() => onDeletePolicy(field.value)}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Delete policy</TooltipContent>
                              </Tooltip>
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
                                Stage: {policyDetails.capture_stage?.replace(/_/g, ' ')}
                              </span>
                            </div>
                            <p className="text-muted-foreground">
                              Owner: {policyDetails.capture_owner?.replace(/_/g, ' ')} • Frequency: {policyDetails.capture_frequency_type?.replace(/_/g, ' ')}
                            </p>
                            {policyDetails.description && (
                              <p className="text-muted-foreground mt-1 text-xs">{policyDetails.description}</p>
                            )}
                          </div>
                        )}
                        <FormDescription>
                          Controls when and how memories are captured
                        </FormDescription>
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryProfile}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select a memory profile" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="">
                              <span className="text-muted-foreground">Default (no schema)</span>
                            </SelectItem>
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
                            {(profileDetails.recommended_model || profileDetails.recommended_provider) && (
                              <p className="text-xs text-muted-foreground mt-1">
                                Recommended: {profileDetails.recommended_provider}/{profileDetails.recommended_model}
                              </p>
                            )}
                          </div>
                        )}
                        <FormDescription>
                          Defines the schema and capture behavior for structured memories
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
                        <FormLabel className="flex items-center gap-2">
                          Memory Agent
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryAgent}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <FormControl>
                          <Input 
                            placeholder="Agent name for memory capture" 
                            {...field} 
                          />
                        </FormControl>
                        <FormDescription>
                          Optional dedicated agent for memory capture
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
                        <FormLabel className="flex items-center gap-2">
                          Memory Run Order
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryRunOrder}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="before_main_response">
                              Before Main Response (memories available during generation)
                            </SelectItem>
                            <SelectItem value="after_main_response">
                              After Main Response (includes current turn)
                            </SelectItem>
                            <SelectItem value="background">
                              Background (async, non-blocking)
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          When memory operations execute relative to agent response
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
                        <FormLabel className="flex items-center gap-2">
                          Default Memory Scope
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryScope}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="conversation">Conversation (isolated to this chat)</SelectItem>
                            <SelectItem value="user">User (cross-conversation)</SelectItem>
                            <SelectItem value="agent">Agent (global for this agent)</SelectItem>
                            <SelectItem value="namespace">Namespace (shared scope)</SelectItem>
                            <SelectItem value="global">Global (all agents)</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          Default visibility boundary for new memories
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
                        <FormLabel className="flex items-center gap-2">
                          Scope Key Template
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.scopeKeyTemplate}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <FormControl>
                          <Input 
                            placeholder="e.g., {{user}}-{{namespace}}" 
                            {...field} 
                          />
                        </FormControl>
                        <FormDescription>
                          Template for generating scope keys using {'{{user}}'}, {'{{agent}}'}, {'{{namespace}}'}
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
                  <CardDescription>Enable tools for explicit memory operations</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="enable_memory_search_tool"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5 pr-4">
                          <FormLabel className="text-base flex items-center gap-2">
                            Memory Search Tool
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">
                                <p>{HELP_TEXT.memorySearchTool}</p>
                              </TooltipContent>
                            </Tooltip>
                          </FormLabel>
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
                        <div className="space-y-0.5 pr-4">
                          <FormLabel className="text-base flex items-center gap-2">
                            Memory Write Tool
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">
                                <p>{HELP_TEXT.memoryWriteTool}</p>
                              </TooltipContent>
                            </Tooltip>
                          </FormLabel>
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
                  <CardTitle className="flex items-center gap-2">
                    Storage Configuration
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        <p>Controls how memories are stored and indexed.</p>
                      </TooltipContent>
                    </Tooltip>
                  </CardTitle>
                  <CardDescription>How memories are indexed and stored</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <FormField
                    control={form.control}
                    name="memory_index_backend_default"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="flex items-center gap-2">
                          Default Index Backend
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.indexBackend}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
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
                          Backend for indexing memories. Hybrid (FTS + Vector) recommended for best results.
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
                        <FormLabel className="flex items-center gap-2">
                          Default Visibility
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.memoryVisibility}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
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
                  <CardTitle className="flex items-center gap-2">
                    Retrieval Settings
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        <p>Controls how memories are retrieved and injected into prompts.</p>
                      </TooltipContent>
                    </Tooltip>
                  </CardTitle>
                  <CardDescription>How memories are retrieved and injected</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <FormField
                    control={form.control}
                    name="memory_retrieval_mode"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="flex items-center gap-2">
                          Retrieval Mode
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.retrievalMode}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
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
                        <FormLabel className="flex items-center gap-2">
                          Max Items to Inject: {field.value || 5}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.maxItemsToInject}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
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
                        <FormLabel className="flex items-center gap-2">
                          Prompt Token Budget: {field.value || 1000} tokens
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <p>{HELP_TEXT.tokenBudget}</p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
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
    </TooltipProvider>
  );
}