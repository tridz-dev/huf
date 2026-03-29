import { useState } from 'react';
import { X, Save, Database, Clock, Filter, FileJson, Settings } from 'lucide-react';
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
import type { MemoryPolicy, MemoryProfile } from '@/types/memory.types';

interface MemoryPolicyFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (policy: Partial<MemoryPolicy>) => void;
  initialData?: MemoryPolicy | null;
  memoryProfiles: MemoryProfile[];
  agentName?: string;
}

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
                    <CardTitle>Policy Identity</CardTitle>
                    <CardDescription>Basic policy information</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-2">
                      <Label htmlFor="policy_name">Policy Name *</Label>
                      <Input
                        id="policy_name"
                        value={formData.policy_name || ''}
                        onChange={(e) => handleChange('policy_name', e.target.value)}
                        placeholder="e.g., Customer Support Memory Policy"
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <Label className="text-base">Enabled</Label>
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
                    <CardTitle>Memory Profile</CardTitle>
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
                    <CardTitle>Capture Configuration</CardTitle>
                    <CardDescription>When and how memories are captured</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="grid gap-2">
                      <Label>Capture Owner</Label>
                      <Select 
                        value={formData.capture_owner} 
                        onValueChange={(value) => handleChange('capture_owner', value as MemoryPolicy['capture_owner'])}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="main_agent">Main Agent</SelectItem>
                          <SelectItem value="memory_agent">Memory Agent (dedicated)</SelectItem>
                          <SelectItem value="post_run_llm">Post-Run LLM</SelectItem>
                          <SelectItem value="rules_only">Rules Only</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-sm text-muted-foreground">
                        Who or what produces the memory content
                      </p>
                    </div>

                    <div className="grid gap-2">
                      <Label>Capture Stage</Label>
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
                      <Label>Capture Frequency</Label>
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
                        <Label>Run Interval: {formData.capture_frequency_value || 1}</Label>
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
                        <Label>Turn Interval: {formData.capture_frequency_value || 1}</Label>
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
                      <Label>Conversation End Strategy</Label>
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
                        <Label>Idle Timeout: {formData.idle_timeout_minutes || 30} minutes</Label>
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
                    <CardTitle>Capture Prompt</CardTitle>
                    <CardDescription>
                      Custom prompt for memory extraction (optional)
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
                    <CardTitle>Indexing Options</CardTitle>
                    <CardDescription>How memories are indexed for retrieval</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <Label className="text-base">Store Raw Payload</Label>
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
                        <Label className="text-base">Store Summary</Label>
                        <p className="text-sm text-muted-foreground">
                          Generate and store a text summary
                        </p>
                      </div>
                      <Switch
                        checked={formData.store_summary}
                        onCheckedChange={(checked) => handleChange('store_summary', checked)}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <Label className="text-base">Enable FTS Index</Label>
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
                        <Label className="text-base">Enable Vector Index</Label>
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
                    <CardTitle>Retrieval Defaults</CardTitle>
                    <CardDescription>Default settings for memory retrieval</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="grid gap-2">
                      <Label>Default Retrieval Mode</Label>
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
                      <Label>Max Items to Inject: {formData.max_items_to_inject}</Label>
                      <Slider
                        min={1}
                        max={20}
                        step={1}
                        value={[formData.max_items_to_inject || 5]}
                        onValueChange={(vals) => handleChange('max_items_to_inject', vals[0])}
                      />
                    </div>

                    <div className="grid gap-2">
                      <Label>Max Tokens to Inject: {formData.max_tokens_to_inject}</Label>
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
                    </CardTitle>
                    <CardDescription>JSON Schema for structured memory capture</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <Label className="text-base">Allow Open Schema</Label>
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
                        <Label className="text-base">Require JSON Schema Match</Label>
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
                    <CardTitle>Update Behavior</CardTitle>
                    <CardDescription>How to handle existing memories</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <Label className="text-base">Allow Update Existing</Label>
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
                        <Label className="text-base">Allow Merge</Label>
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
                        <Label className="text-base">Allow Append</Label>
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
                      <Label>Minimum Confidence: {formData.min_confidence}</Label>
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
  );
}
