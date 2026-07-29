import { useMemo } from 'react';
import { UseFormReturn } from 'react-hook-form';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { linkRoutes } from '@/lib/link-routes';
import {
  memoryScopeTypes,
  memoryDefaultStatuses,
  memoryInjectModes,
  type MemoryPolicyFormValues,
} from './memoryPolicyFormSchema';

interface AgentOption {
  name: string;
  agent_name?: string;
}

interface KnowledgeSourceOption {
  name: string;
  source_name?: string;
}

interface MemoryPolicyFieldsProps {
  form: UseFormReturn<MemoryPolicyFormValues>;
  isNew: boolean;
  agents: AgentOption[];
  knowledgeSources: KnowledgeSourceOption[];
}

function SwitchField({
  form,
  name,
  label,
  description,
}: {
  form: UseFormReturn<MemoryPolicyFormValues>;
  name: 'enabled' | 'approval_required' | 'allow_agent_write' | 'allow_user_scope_write' |
    'allow_role_scope_write' | 'allow_agent_scope_write' | 'allow_site_scope_write' |
    'auto_promote_to_knowledge';
  label: string;
  description: string;
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
          <div className="space-y-0.5 pr-4">
            <FormLabel className="text-base">{label}</FormLabel>
            <FormDescription>{description}</FormDescription>
          </div>
          <FormControl>
            <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
          </FormControl>
        </FormItem>
      )}
    />
  );
}

export function MemoryPolicyFields({ form, isNew, agents, knowledgeSources }: MemoryPolicyFieldsProps) {
  const watchAutoPromote = form.watch('auto_promote_to_knowledge');

  const agentOptions: ComboboxOption[] = useMemo(
    () => agents.map((a) => ({ value: a.name, label: a.agent_name || a.name })),
    [agents],
  );
  const knowledgeSourceOptions: ComboboxOption[] = useMemo(
    () => knowledgeSources.map((k) => ({ value: k.name, label: k.source_name || k.name })),
    [knowledgeSources],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Policy</CardTitle>
          <CardDescription>
            Identify this policy and choose which agent (if any) it is dedicated to.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {isNew && (
            <FormField
              control={form.control}
              name="policy_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Policy Name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. support-agent-memory" {...field} />
                  </FormControl>
                  <FormDescription>Unique identifier for this memory policy.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <SwitchField
            form={form}
            name="enabled"
            label="Enabled"
            description="Only enabled policies are selectable from an agent's Memory settings and are evaluated at runtime."
          />

          <div className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="agent"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Agent</FormLabel>
                  <FormControl>
                    <Combobox
                      options={agentOptions}
                      value={field.value}
                      onValueChange={(v) => field.onChange(v || undefined)}
                      placeholder="Any agent"
                      searchPlaceholder="Search agents..."
                      emptyText="No agents found."
                      linkTo={linkRoutes.agent}
                    />
                  </FormControl>
                  <FormDescription>
                    Optional. Restricts this policy to a single agent instead of being reusable
                    across any agent that selects it.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="scope_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Scope Type</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {memoryScopeTypes.map((scope) => (
                        <SelectItem key={scope} value={scope}>
                          {scope}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Determines which "bucket" memory records are grouped under: a single
                    conversation, a user, a role, an agent, a workspace, a site, or globally.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="scope_key"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Scope Key</FormLabel>
                <FormControl>
                  <Input placeholder="Leave empty to use runtime context" {...field} />
                </FormControl>
                <FormDescription>
                  Optional fixed scope key. If empty, the runtime context (current user, agent, or
                  site) decides the key at conversation time.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Capture</CardTitle>
          <CardDescription>Control how new memory records are created and approved.</CardDescription>
          {/*
            Capture Mode + Learning Agent (background extraction, delegated to a
            dedicated agent) intentionally live outside this form for now — the
            doctype fields exist but nothing reads them at runtime yet. See
            frontend/docs/MEMORY_POLICY_CAPTURE_DELEGATION.md for the design and
            the UI code to reintroduce once the extraction job is built. That doc
            also proposes switching this form to tabs (Policy/Capture/Retrieval/
            Guardrails) once Capture grows enough to justify it.
          */}
        </CardHeader>
        <CardContent className="grid gap-6">
          <SwitchField
            form={form}
            name="approval_required"
            label="Approval Required"
            description="New memory records start as pending and must be approved by a user before becoming active. Turn this off to trust captured memory automatically."
          />

          <FormField
            control={form.control}
            name="default_status"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Default Status</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {memoryDefaultStatuses.map((status) => (
                      <SelectItem key={status} value={status}>
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  Status assigned to newly captured memory records before any approval step runs.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="allowed_record_types"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Allowed Record Types</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder={'One record type per line, e.g.\nfact\npreference\ninstruction'}
                    className="min-h-[80px] resize-y font-mono text-sm"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Optional newline-separated list of record types this policy may capture. Leave
                  empty to allow all types.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retrieval</CardTitle>
          <CardDescription>
            Control how much memory is pulled back into the agent's context.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="inject_mode"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Inject Mode</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {memoryInjectModes.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {mode}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  <span className="block"><strong>Never</strong> — memory is never added to the prompt.</span>
                  <span className="block"><strong>Relevant Only</strong> — only records relevant to the current turn are injected.</span>
                  <span className="block"><strong>Always</strong> — every active memory record for the scope is injected on every turn.</span>
                  <span className="block"><strong>Tool Only</strong> — memory is not auto-injected; the agent must call a memory tool to read it.</span>
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid gap-6 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="max_records"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Max Records</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      {...field}
                      onChange={(e) => field.onChange(Number(e.target.value))}
                    />
                  </FormControl>
                  <FormDescription>
                    Maximum number of memory records retrieved for a single turn.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="token_budget"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Token Budget</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      {...field}
                      onChange={(e) => field.onChange(Number(e.target.value))}
                    />
                  </FormControl>
                  <FormDescription>
                    Maximum tokens of memory content allowed into the prompt per turn.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Write Permissions</CardTitle>
          <CardDescription>
            Control which scopes this policy is allowed to write memory records into.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <SwitchField
            form={form}
            name="allow_agent_write"
            label="Allow Agent Write"
            description="Lets the agent itself write memory records (via a tool call), not just users."
          />
          <SwitchField
            form={form}
            name="allow_user_scope_write"
            label="Allow User Scope Write"
            description="Permits writing memory records scoped to the current user."
          />
          <SwitchField
            form={form}
            name="allow_role_scope_write"
            label="Allow Role Scope Write"
            description="Permits writing memory records scoped to a role, shared across all users with it."
          />
          <SwitchField
            form={form}
            name="allow_agent_scope_write"
            label="Allow Agent Scope Write"
            description="Permits writing memory records scoped to the agent, shared across all its conversations."
          />
          <SwitchField
            form={form}
            name="allow_site_scope_write"
            label="Allow Site Scope Write"
            description="Permits writing memory records scoped globally to this site. Use sparingly."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge Projection</CardTitle>
          <CardDescription>
            Optionally promote high-confidence memories into a permanent Knowledge Source.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <SwitchField
            form={form}
            name="auto_promote_to_knowledge"
            label="Auto Promote to Knowledge"
            description="Automatically copies memory records that clear the confidence and importance thresholds below into a Knowledge Source, making them retrievable outside the memory system."
          />

          {watchAutoPromote && (
            <>
              <FormField
                control={form.control}
                name="knowledge_source"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Knowledge Source</FormLabel>
                    <FormControl>
                      <Combobox
                        options={knowledgeSourceOptions}
                        value={field.value}
                        onValueChange={(v) => field.onChange(v || undefined)}
                        placeholder="Select a Knowledge Source"
                        searchPlaceholder="Search knowledge sources..."
                        emptyText="No knowledge sources found."
                        linkTo={linkRoutes.knowledgeSource}
                      />
                    </FormControl>
                    <FormDescription>
                      Required when Auto Promote is enabled. The Knowledge Source that promoted
                      memories are written into.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid gap-6 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="promotion_min_confidence"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Min Confidence</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={1}
                          step={0.05}
                          {...field}
                          onChange={(e) => field.onChange(Number(e.target.value))}
                        />
                      </FormControl>
                      <FormDescription>
                        Minimum confidence score (0-1) a memory record must have to be promoted.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="promotion_min_importance"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Min Importance</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={1}
                          step={0.05}
                          {...field}
                          onChange={(e) => field.onChange(Number(e.target.value))}
                        />
                      </FormControl>
                      <FormDescription>
                        Minimum importance score (0-1) a memory record must have to be promoted.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Lifecycle</CardTitle>
          <CardDescription>Control how long memory records live under this policy.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="ttl_days"
            render={({ field }) => (
              <FormItem>
                <FormLabel>TTL Days</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    {...field}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                  />
                </FormControl>
                <FormDescription>
                  Number of days before a memory record expires and is archived. 0 means memory
                  never expires automatically.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="metadata_json"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Metadata JSON</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="{}"
                    className="min-h-[100px] resize-y font-mono text-sm"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Optional free-form JSON for policy-specific settings not covered above, consumed
                  by custom tooling or automations.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
