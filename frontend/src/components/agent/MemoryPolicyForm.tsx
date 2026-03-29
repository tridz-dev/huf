import { useState } from 'react';
import { X, Save, Database, Clock, Filter, FileJson, Settings, HelpCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { MemoryPolicy, MemoryProfile } from '@/types/memory.types';

interface MemoryPolicyFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (policy: Partial<MemoryPolicy>) => void;
  initialData?: MemoryPolicy | null;
  memoryProfiles: MemoryProfile[];
  agentName?: string;
}

// Help text definitions
const HELP_TEXT = {
  policyName: "A unique, descriptive name for this policy. Use names that clearly indicate the policy's purpose.",
  enabled: "Enable or disable this policy. Disabled policies won't capture memories even if assigned to agents.",
  memoryProfile: "The memory profile that defines the schema and default behavior for this policy.",
  captureOwner: "Who produces the memory: main_agent (the agent itself), memory_agent (dedicated agent), post_run_llm (separate LLM), or rules_only (no LLM).",
  captureStage: "When memory capture occurs: in_prompt (during generation), post_response_sync (immediately after), post_response_async (background), conversation_end, or scheduled.",
  captureFrequency: "How often to capture: every_run (each time), every_n_runs (periodic), every_n_turns (after N messages), conversation_end, manual (explicit only), or scheduled.",
  frequencyValue: "The N value for 'every_n_runs' or 'every_n_turns'. E.g., 3 means capture every 3rd run/turn.",
  conversationEndStrategy: "How to determine when a conversation ends: manual_close (user action), idle_timeout (inactivity), heuristic (AI detection), or never.",
  idleTimeout: "Minutes of inactivity before considering the conversation ended. Memories are captured at timeout.",
  capturePrompt: "Custom prompt to guide memory extraction. Be specific about what to capture and how to format it.",
  storeRawPayload: "Keep the original raw capture output. Useful for debugging but increases storage.",
  storeSummary: "Generate and store a text summary. Enables text search and human review.",
  enableFts: "Enable Full-Text Search indexing for keyword-based retrieval.",
  enableVector: "Enable vector/semantic indexing for similarity-based retrieval. Requires more storage.",
  retrievalMode: "How memories are provided to agents: inject (auto-include), tool_only (agent requests), or hybrid (both).",
  maxItems: "Maximum memories to include in a single prompt. Prevents context overflow.",
  maxTokens: "Maximum tokens for injected memories. Acts as a budget to prevent exceeding context limits.",
  openSchema: "Accept any JSON structure without validation. Useful for flexible capture but may be inconsistent.",
  requireSchemaMatch: "Validate captured memories against the JSON Schema. Reject non-matching memories.",
  allowUpdate: "Update existing memories when similar content is captured. Prevents duplicates.",
  allowMerge: "Merge new data with existing memories rather than replacing. Good for accumulating info.",
  allowAppend: "Append to lists within existing memories. Useful for collecting multiple items.",
  minConfidence: "Minimum confidence score (0-1) for accepting memories. Higher = fewer but higher quality memories.",
  jsonSchema: "JSON Schema for validating captured memories. Defines the expected structure.",
};

const defaultPolicy: Partial<MemoryPolicy> = {
  policy_name: '',
  enabled: true,
  capture_owner: 'main_agent',
  capture_stage: 'post_response_async',
  capture_frequency_type: 'conversation_end',
  conversation_end_strategy: 'idle_timeout',
  idle_timeout_minutes: 30,
  allow_open_schema: false,
  require_json_schema_match: true,
  allow_update_existing: true,
  allow_merge: true,
  allow_append: false,
  min_confidence: 0.7,
  store_raw_payload: true,
  store_summary: true,
  enable_fts_index: true,
  enable_vector_index: true,
  retrieval_mode_default: 'hybrid',
  max_items_to_inject: 5,
  max_tokens_to_inject: 2000,
};

export function MemoryPolicyForm({
  isOpen,
  onClose,
  onSave,
  initialData,
  memoryProfiles,
  agentName,
}: MemoryPolicyFormProps) {
  const [activeTab, setActiveTab] = useState('general');
  const [formData, setFormData] = useState<Partial<MemoryPolicy>>(initialData || defaultPolicy);
  const [jsonSchemaText, setJsonSchemaText] = useState(
    initialData?.capture_schema_json 
      ? JSON.stringify(initialData.capture_schema_json, null, 2)
      : '{}'
  );
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const isEditing = !!initialData;

  const handleChange = <K extends keyof MemoryPolicy>(
    field: K,
    value: MemoryPolicy[K]
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleJsonSchemaChange = (value: string) => {
    setJsonSchemaText(value);
    try {
      const parsed = JSON.parse(value);
      setFormData((prev) => ({ ...prev, capture_schema_json: parsed }));
      setSchemaError(null);
    } catch (e) {
      setSchemaError('Invalid JSON format');
    }
  };

  const handleSubmit = () => {
    // Validate required fields
    if (!formData.policy_name?.trim()) {
      return;
    }
    
    onSave({
      ...formData,
      agent: agentName,
    });
    onClose();
  };

  const handleClose = () => {
    setFormData(initialData || defaultPolicy);
    setJsonSchemaText(
      initialData?.capture_schema_json 
        ? JSON.stringify(initialData.capture_schema_json, null, 2)
        : '{}'
    );
    setSchemaError(null);
    setActiveTab('general');
    onClose();
  };

  return (
    <TooltipProvider delayDuration={100}>
      <Dialog open={isOpen} onOpenChange={handleClose}>
        <DialogContent className="max-w-4xl max-h-[90vh] p-0">
          <DialogHeader className="px-6 pt-6 pb-2">
            <div className="flex items-center justify-between">
              <div>
                <DialogTitle className="flex items-center gap-2">
                  <Database className="w-5 h-5" />
                  {isEditing ? 'Edit Memory Policy' : 'Create Memory Policy'}
                </DialogTitle>
                <DialogDescription>
                  {isEditing 
                    ? 'Update memory capture configuration' 
                    : 'Configure when and how memories are captured'}
                </DialogDescription>
              </div>
              <Button variant="ghost" size="icon" onClick={handleClose}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-4 px-6">
              <TabsTrigger value="general">
                <Settings className="w-4 h-4 mr-2" />
                General
              </TabsTrigger>
              <TabsTrigger value="capture">
                <Clock className="w-4 h-4 mr-2" />
                Capture
              </TabsTrigger>
              <TabsTrigger value="storage">
                <Database className="w-4 h-4 mr-2" />
                Storage
              </TabsTrigger>
              <TabsTrigger value="advanced">
                <Filter className="w-4 h-4 mr-2" />
                Advanced
              </TabsTrigger>
            </TabsList>

            <ScrollArea className="h-[60vh]">
              <div className="px-6 pb-6">
                {/* General Tab */}
                <TabsContent value="general" className="space-y-6 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Policy Identity
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>Basic information about this policy</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>Basic policy information</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid gap-2">
                        <Label htmlFor="policy_name" className="flex items-center gap-2">
                          Policy Name *
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.policyName}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Input
                          id="policy_name"
                          value={formData.policy_name || ''}
                          onChange={(e) => handleChange('policy_name', e.target.value)}
                          placeholder="e.g., Customer Support Memory Policy"
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Enabled
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.enabled}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Enable memory capture with this policy
                          </p>
                        </div>
                        <Switch
                          checked={formData.enabled}
                          onCheckedChange={(checked) => handleChange('enabled', checked)}
                        />
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Memory Profile
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">{HELP_TEXT.memoryProfile}</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>Select a schema profile for structured capture</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid gap-2">
                        <Label>Profile</Label>
                        <Select 
                          value={formData.memory_profile || ''} 
                          onValueChange={(value) => handleChange('memory_profile', value || undefined)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a profile (optional)" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="">None (flexible schema)</SelectItem>
                            {memoryProfiles.map((profile) => (
                              <SelectItem key={profile.name} value={profile.name}>
                                {profile.icon && <span className="mr-2">{profile.icon}</span>}
                                {profile.profile_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        
                        {formData.memory_profile && (
                          <div className="mt-2 p-3 bg-muted/50 rounded-md">
                            {(() => {
                              const profile = memoryProfiles.find(p => p.name === formData.memory_profile);
                              return profile ? (
                                <div className="space-y-2">
                                  <div className="flex items-center gap-2">
                                    {profile.icon && <span className="text-lg">{profile.icon}</span>}
                                    <Badge variant="outline">{profile.category}</Badge>
                                    {profile.is_system_profile && (
                                      <Badge variant="secondary">System</Badge>
                                    )}
                                  </div>
                                  <p className="text-sm text-muted-foreground">
                                    {profile.description}
                                  </p>
                                  {profile.recommended_model && (
                                    <p className="text-xs text-muted-foreground">
                                      Recommended: {profile.recommended_provider}/{profile.recommended_model}
                                    </p>
                                  )}
                                </div>
                              ) : null;
                            })()}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Capture Tab */}
                <TabsContent value="capture" className="space-y-6 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Capture Configuration
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>When and how memories are captured</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>When and how memories are captured</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Capture Owner
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.captureOwner}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Select 
                          value={formData.capture_owner} 
                          onValueChange={(value) => handleChange('capture_owner', value as MemoryPolicy['capture_owner'])}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="main_agent">Main Agent (self-capture)</SelectItem>
                            <SelectItem value="memory_agent">Memory Agent (dedicated)</SelectItem>
                            <SelectItem value="post_run_llm">Post-Run LLM (separate call)</SelectItem>
                            <SelectItem value="rules_only">Rules Only (no LLM)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Capture Stage
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.captureStage}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Select 
                          value={formData.capture_stage} 
                          onValueChange={(value) => handleChange('capture_stage', value as MemoryPolicy['capture_stage'])}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="in_prompt">In Prompt (synchronous)</SelectItem>
                            <SelectItem value="post_response_sync">Post Response (sync)</SelectItem>
                            <SelectItem value="post_response_async">Post Response (async)</SelectItem>
                            <SelectItem value="conversation_end">Conversation End</SelectItem>
                            <SelectItem value="scheduled">Scheduled</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Capture Frequency
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.captureFrequency}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Select 
                          value={formData.capture_frequency_type} 
                          onValueChange={(value) => handleChange('capture_frequency_type', value as MemoryPolicy['capture_frequency_type'])}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="every_run">Every Run</SelectItem>
                            <SelectItem value="every_n_runs">Every N Runs</SelectItem>
                            <SelectItem value="every_n_turns">Every N Turns</SelectItem>
                            <SelectItem value="conversation_end">Conversation End</SelectItem>
                            <SelectItem value="manual">Manual Only</SelectItem>
                            <SelectItem value="scheduled">Scheduled</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {formData.capture_frequency_type === 'every_n_runs' && (
                        <div className="grid gap-2">
                          <Label className="flex items-center gap-2">
                            Run Interval: {formData.capture_frequency_value || 1}
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.frequencyValue}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <Slider
                            min={1}
                            max={10}
                            step={1}
                            value={[formData.capture_frequency_value || 1]}
                            onValueChange={(vals) => handleChange('capture_frequency_value', vals[0])}
                          />
                        </div>
                      )}

                      {formData.capture_frequency_type === 'every_n_turns' && (
                        <div className="grid gap-2">
                          <Label className="flex items-center gap-2">
                            Turn Interval: {formData.capture_frequency_value || 1}
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.frequencyValue}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <Slider
                            min={1}
                            max={20}
                            step={1}
                            value={[formData.capture_frequency_value || 1]}
                            onValueChange={(vals) => handleChange('capture_frequency_value', vals[0])}
                          />
                        </div>
                      )}

                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Conversation End Strategy
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.conversationEndStrategy}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Select 
                          value={formData.conversation_end_strategy} 
                          onValueChange={(value) => handleChange('conversation_end_strategy', value as MemoryPolicy['conversation_end_strategy'])}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="manual_close">Manual Close</SelectItem>
                            <SelectItem value="idle_timeout">Idle Timeout</SelectItem>
                            <SelectItem value="heuristic">Heuristic Detection</SelectItem>
                            <SelectItem value="never">Never Auto-End</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {formData.conversation_end_strategy === 'idle_timeout' && (
                        <div className="grid gap-2">
                          <Label className="flex items-center gap-2">
                            Idle Timeout: {formData.idle_timeout_minutes || 30} minutes
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.idleTimeout}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <Slider
                            min={5}
                            max={120}
                            step={5}
                            value={[formData.idle_timeout_minutes || 30]}
                            onValueChange={(vals) => handleChange('idle_timeout_minutes', vals[0])}
                          />
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Capture Prompt
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">{HELP_TEXT.capturePrompt}</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>
                        Custom prompt for memory extraction
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Textarea
                        value={formData.capture_prompt || ''}
                        onChange={(e) => handleChange('capture_prompt', e.target.value)}
                        placeholder="Custom instructions for extracting memories from conversation..."
                        className="min-h-[150px]"
                      />
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Storage Tab */}
                <TabsContent value="storage" className="space-y-6 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Storage Options
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>What data to store with each memory</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>What data to store with each memory</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Store Raw Payload
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.storeRawPayload}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Keep the original raw capture data
                          </p>
                        </div>
                        <Switch
                          checked={formData.store_raw_payload}
                          onCheckedChange={(checked) => handleChange('store_raw_payload', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Store Summary
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.storeSummary}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Generate and store a text summary
                          </p>
                        </div>
                        <Switch
                          checked={formData.store_summary}
                          onCheckedChange={(checked) => handleChange('store_summary', checked)}
                        />
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Indexing Options
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>How memories are indexed for search</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>How memories are indexed for search</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Enable FTS Index
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.enableFts}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Full-text search indexing for keyword queries
                          </p>
                        </div>
                        <Switch
                          checked={formData.enable_fts_index}
                          onCheckedChange={(checked) => handleChange('enable_fts_index', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Enable Vector Index
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.enableVector}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Semantic search via vector embeddings
                          </p>
                        </div>
                        <Switch
                          checked={formData.enable_vector_index}
                          onCheckedChange={(checked) => handleChange('enable_vector_index', checked)}
                        />
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Retrieval Defaults
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>Default settings for memory retrieval</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>Default settings for memory retrieval</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Default Retrieval Mode
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.retrievalMode}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Select 
                          value={formData.retrieval_mode_default} 
                          onValueChange={(value) => handleChange('retrieval_mode_default', value as MemoryPolicy['retrieval_mode_default'])}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="inject">Inject (auto-include)</SelectItem>
                            <SelectItem value="tool_only">Tool Only (on request)</SelectItem>
                            <SelectItem value="hybrid">Hybrid (both)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Max Items to Inject: {formData.max_items_to_inject}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.maxItems}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Slider
                          min={1}
                          max={20}
                          step={1}
                          value={[formData.max_items_to_inject || 5]}
                          onValueChange={(vals) => handleChange('max_items_to_inject', vals[0])}
                        />
                      </div>

                      <div className="grid gap-2">
                        <Label className="flex items-center gap-2">
                          Max Tokens to Inject: {formData.max_tokens_to_inject}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.maxTokens}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Slider
                          min={100}
                          max={8000}
                          step={100}
                          value={[formData.max_tokens_to_inject || 2000]}
                          onValueChange={(vals) => handleChange('max_tokens_to_inject', vals[0])}
                        />
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Advanced Tab */}
                <TabsContent value="advanced" className="space-y-6 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <FileJson className="w-5 h-5" />
                        Schema Configuration
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">{HELP_TEXT.jsonSchema}</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>JSON Schema for structured memory capture</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Allow Open Schema
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.openSchema}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Accept any JSON structure without validation
                          </p>
                        </div>
                        <Switch
                          checked={formData.allow_open_schema}
                          onCheckedChange={(checked) => handleChange('allow_open_schema', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Require JSON Schema Match
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.requireSchemaMatch}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Validate captured data against the schema
                          </p>
                        </div>
                        <Switch
                          checked={formData.require_json_schema_match}
                          onCheckedChange={(checked) => handleChange('require_json_schema_match', checked)}
                        />
                      </div>

                      {!formData.allow_open_schema && (
                        <div className="grid gap-2">
                          <Label>Custom JSON Schema</Label>
                          <Textarea
                            value={jsonSchemaText}
                            onChange={(e) => handleJsonSchemaChange(e.target.value)}
                            className={`min-h-[300px] font-mono text-sm ${schemaError ? 'border-red-500' : ''}`}
                            placeholder={`{\n  "type": "object",\n  "properties": {\n    "key": { "type": "string" }\n  }\n}`}
                          />
                          {schemaError && (
                            <p className="text-sm text-red-500">{schemaError}</p>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        Update Behavior
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="w-4 h-4 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>How to handle existing memories</TooltipContent>
                        </Tooltip>
                      </CardTitle>
                      <CardDescription>How to handle existing memories</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Allow Update Existing
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.allowUpdate}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Update memories when similar content is captured
                          </p>
                        </div>
                        <Switch
                          checked={formData.allow_update_existing}
                          onCheckedChange={(checked) => handleChange('allow_update_existing', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Allow Merge
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.allowMerge}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Merge new data with existing memories
                          </p>
                        </div>
                        <Switch
                          checked={formData.allow_merge}
                          onCheckedChange={(checked) => handleChange('allow_merge', checked)}
                        />
                      </div>

                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <Label className="text-base flex items-center gap-2">
                            Allow Append
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">{HELP_TEXT.allowAppend}</TooltipContent>
                            </Tooltip>
                          </Label>
                          <p className="text-sm text-muted-foreground">
                            Append to lists within existing memories
                          </p>
                        </div>
                        <Switch
                          checked={formData.allow_append}
                          onCheckedChange={(checked) => handleChange('allow_append', checked)}
                        />
                      </div>

                      <div className="grid gap-2 pt-4">
                        <Label className="flex items-center gap-2">
                          Minimum Confidence: {formData.min_confidence}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-4 h-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">{HELP_TEXT.minConfidence}</TooltipContent>
                          </Tooltip>
                        </Label>
                        <Slider
                          min={0}
                          max={1}
                          step={0.05}
                          value={[formData.min_confidence || 0.7]}
                          onValueChange={(vals) => handleChange('min_confidence', vals[0])}
                        />
                        <p className="text-sm text-muted-foreground">
                          Memories below this confidence threshold will be rejected
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>
              </div>
            </ScrollArea>
          </Tabs>

          {/* Footer Actions */}
          <div className="flex justify-end gap-3 px-6 py-4 border-t">
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button 
              onClick={handleSubmit}
              disabled={!formData.policy_name?.trim() || !!schemaError}
            >
              <Save className="w-4 h-4 mr-2" />
              {isEditing ? 'Update Policy' : 'Create Policy'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}