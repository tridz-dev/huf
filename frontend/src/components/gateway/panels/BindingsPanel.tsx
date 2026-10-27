import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { getAgents } from '@/services/agentApi';
import { getFlowDefinitions } from '@/services/flowApi';
import type { GatewayProvider } from '@/services/gatewayApi';
import {
  MATCH_TYPES,
  bindingFormSchema,
  deleteBinding,
  describeRule,
  listBindings,
  listSlackChannels,
  listSlackUsers,
  moveItem,
  reorderBindings,
  saveBinding,
  sortByPriority,
  testRoute,
  type BindingFormValues,
  type GatewayBinding,
  type PickerItem,
  type RoutePreview,
} from '@/services/gatewayBindingsApi';
import { registerProviderPanel, type ProviderPanelProps } from './index';

const PROVIDERS: GatewayProvider[] = [
  'WhatsApp', 'Messenger', 'Instagram', 'Telegram', 'Slack', 'Email', 'Google Chat', 'Microsoft Teams',
];

const MATCH_LABELS: Record<(typeof MATCH_TYPES)[number], string> = {
  'Any conversation': 'Any conversation',
  'Direct message': 'A direct message',
  'Room or channel': 'A room or channel',
  Thread: 'A thread',
  Sender: 'A person',
};

interface Option { value: string; label: string }

function useTargets() {
  const [agents, setAgents] = useState<Option[]>([]);
  const [flows, setFlows] = useState<Option[]>([]);
  useEffect(() => {
    getAgents()
      .then((res) => {
        const list = Array.isArray(res) ? res : res.items;
        setAgents(list.map((a) => ({ value: a.name, label: a.agent_name || a.name })));
      })
      .catch(() => setAgents([]));
    getFlowDefinitions()
      .then((res) => setFlows(res.map((f) => ({ value: f.name, label: f.flow_name || f.name }))))
      .catch(() => setFlows([]));
  }, []);
  return { agents, flows };
}

function SlackPicker({
  gateway, kind, value, onChange,
}: { gateway: string; kind: 'channels' | 'users'; value: string; onChange: (v: string) => void }) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<PickerItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      const fetcher = kind === 'channels' ? listSlackChannels : listSlackUsers;
      fetcher(gateway, query || undefined)
        .then((res) => {
          if (cancelled) return;
          setItems(res.items);
          setError(res.error);
        })
        .catch(() => !cancelled && setError('Could not load the list from Slack.'));
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [gateway, kind, query]);

  const options: ComboboxOption[] = useMemo(() => {
    const opts = items.map((i) => ({ value: i.id, label: i.label, subtitle: i.is_member ? undefined : 'Not joined' }));
    if (value && !opts.some((o) => o.value === value)) opts.unshift({ value, label: value, subtitle: undefined });
    return opts;
  }, [items, value]);

  return (
    <div className="space-y-2">
      <Combobox
        options={options}
        value={value}
        onValueChange={onChange}
        onSearchChange={setQuery}
        shouldFilter={false}
        placeholder={kind === 'channels' ? 'Choose a channel' : 'Choose a person'}
        searchPlaceholder={kind === 'channels' ? 'Search channels...' : 'Search people...'}
        emptyText="No matches."
      />
      {error && <p className="text-xs text-muted-foreground">{error} You can also paste an ID below.</p>}
      {error && <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder="Slack ID" />}
    </div>
  );
}

function BindingDialog({
  gateway, provider, rule, agents, flows, onClose, onSaved,
}: {
  gateway: string;
  provider: GatewayProvider;
  rule: GatewayBinding | null;
  agents: Option[];
  flows: Option[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const form = useForm<BindingFormValues>({
    resolver: zodResolver(bindingFormSchema),
    defaultValues: {
      match_type: rule?.match_type ?? 'Room or channel',
      match_value: rule?.match_value ?? '',
      target_type: rule?.target_type ?? 'Agent',
      agent: rule?.agent ?? '',
      flow: rule?.flow ?? '',
      description: rule?.description ?? '',
    },
  });
  const matchType = form.watch('match_type');
  const targetType = form.watch('target_type');
  const isSlack = provider === 'Slack';
  const pickerKind = matchType === 'Sender' || matchType === 'Direct message' ? 'users' : 'channels';

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await saveBinding(gateway, {
        ...values,
        name: rule?.name,
        match_value: values.match_type === 'Any conversation' ? '' : values.match_value,
        agent: values.target_type === 'Agent' ? values.agent : '',
        flow: values.target_type === 'Flow' ? values.flow : '',
        is_enabled: rule?.is_enabled ?? 1,
      });
      toast.success('Rule saved');
      onSaved();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save the rule');
    }
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{rule ? 'Edit rule' : 'Add a rule'}</DialogTitle></DialogHeader>
        <Form {...form}>
          <form onSubmit={onSubmit} className="space-y-4">
            <FormField control={form.control} name="match_type" render={({ field }) => (
              <FormItem>
                <FormLabel>When a message comes from</FormLabel>
                <Select value={field.value} onValueChange={(v) => { field.onChange(v); form.setValue('match_value', ''); }}>
                  <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                  <SelectContent>
                    {MATCH_TYPES.map((t) => <SelectItem key={t} value={t}>{MATCH_LABELS[t]}</SelectItem>)}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )} />
            {matchType !== 'Any conversation' && (
              <FormField control={form.control} name="match_value" render={({ field }) => (
                <FormItem>
                  <FormLabel>{matchType === 'Sender' ? 'Person' : matchType === 'Thread' ? 'Thread ID' : 'Conversation'}</FormLabel>
                  {isSlack && matchType !== 'Thread' ? (
                    <SlackPicker gateway={gateway} kind={pickerKind} value={field.value ?? ''} onChange={field.onChange} />
                  ) : (
                    <FormControl><Input {...field} value={field.value ?? ''} placeholder="Enter the ID" /></FormControl>
                  )}
                  <FormMessage />
                </FormItem>
              )} />
            )}
            <FormField control={form.control} name="target_type" render={({ field }) => (
              <FormItem>
                <FormLabel>Send it to</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                  <SelectContent>
                    <SelectItem value="Agent">An agent</SelectItem>
                    <SelectItem value="Flow">A flow</SelectItem>
                  </SelectContent>
                </Select>
              </FormItem>
            )} />
            {targetType === 'Agent' ? (
              <FormField control={form.control} name="agent" render={({ field }) => (
                <FormItem>
                  <FormLabel>Agent</FormLabel>
                  <Combobox options={agents} value={field.value} onValueChange={field.onChange} placeholder="Choose an agent" />
                  <FormMessage />
                </FormItem>
              )} />
            ) : (
              <FormField control={form.control} name="flow" render={({ field }) => (
                <FormItem>
                  <FormLabel>Flow</FormLabel>
                  <Combobox options={flows} value={field.value} onValueChange={field.onChange} placeholder="Choose a flow" />
                  <FormMessage />
                </FormItem>
              )} />
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>Save rule</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

function TestBox({ gateway }: { gateway: string }) {
  const [conversation, setConversation] = useState('');
  const [sender, setSender] = useState('');
  const [thread, setThread] = useState('');
  const [result, setResult] = useState<RoutePreview | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await testRoute(gateway, {
        conversation_id: conversation, sender_id: sender, thread_id: thread,
      }));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not test this message');
    } finally {
      setBusy(false);
    }
  };

  let outcome = '';
  if (result) {
    if (result.status === 'Queued') {
      const target = result.agent ?? result.flow;
      outcome = result.binding
        ? `This message would go to ${target} (rule ${result.binding}).`
        : `No rule matches, so it would go to the default: ${target}.`;
    } else {
      outcome = result.reason ?? 'This message would not be handled.';
    }
  }

  return (
    <div className="space-y-2 rounded-md border p-3">
      <p className="text-sm font-medium">Test a message</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <Input aria-label="Conversation ID" value={conversation} onChange={(e) => setConversation(e.target.value)} placeholder="Conversation ID" />
        <Input aria-label="Sender ID" value={sender} onChange={(e) => setSender(e.target.value)} placeholder="Sender ID" />
        <Input aria-label="Thread ID" value={thread} onChange={(e) => setThread(e.target.value)} placeholder="Thread ID (optional)" />
      </div>
      <Button size="sm" variant="secondary" onClick={run} disabled={busy}>See which rule matches</Button>
      {result && <p className="text-sm text-muted-foreground" role="status">{outcome}</p>}
    </div>
  );
}

export function BindingsPanel({ gateway }: ProviderPanelProps) {
  const gw = gateway.name;
  const { agents, flows } = useTargets();
  const [rules, setRules] = useState<GatewayBinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<GatewayBinding | 'new' | null>(null);
  const [deleting, setDeleting] = useState<GatewayBinding | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setRules(sortByPriority(await listBindings(gw)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load routing rules');
    }
  }, [gw]);

  useEffect(() => { void load(); }, [load]);

  const move = async (index: number, delta: number) => {
    if (!rules) return;
    const next = moveItem(rules, index, delta);
    setRules(next);
    try {
      setRules(sortByPriority(await reorderBindings(gw, next.map((r) => r.name))));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not reorder rules');
      void load();
    }
  };

  const toggle = async (rule: GatewayBinding, enabled: boolean) => {
    try {
      await saveBinding(gw, { ...rule, match_value: rule.match_value ?? '', agent: rule.agent ?? '', flow: rule.flow ?? '', description: rule.description ?? '', is_enabled: enabled ? 1 : 0 });
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update the rule');
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await deleteBinding(deleting.name);
      toast.success('Rule deleted');
      setDeleting(null);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not delete the rule');
    }
  };

  const nameOf = (list: Option[], v?: string | null) => list.find((o) => o.value === v)?.label ?? v ?? '';

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Rules are checked from top to bottom. The first match decides where a message goes.
      </p>
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      {!rules && !error && <Skeleton className="h-16 w-full" />}
      {rules && rules.length === 0 && (
        <p className="text-sm text-muted-foreground">No rules yet. Every message goes to the default.</p>
      )}
      {rules && rules.length > 0 && (
        <ul className="divide-y rounded-md border">
          {rules.map((rule, index) => (
            <li key={rule.name} className="flex items-center gap-2 p-2">
              <div className="flex flex-col">
                <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp className="h-3 w-3" /></Button>
                <Button size="icon-sm" variant="ghost" aria-label="Move down" disabled={index === rules.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-3 w-3" /></Button>
              </div>
              <p className="flex-1 text-sm">
                {describeRule(
                  { ...rule, agent: nameOf(agents, rule.agent), flow: nameOf(flows, rule.flow) }
                )}
              </p>
              <Switch checked={!!rule.is_enabled} onCheckedChange={(v) => toggle(rule, v)} aria-label="Rule enabled" />
              <Button size="icon" variant="ghost" aria-label="Edit rule" onClick={() => setEditing(rule)}><Pencil className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" aria-label="Delete rule" onClick={() => setDeleting(rule)}><Trash2 className="h-4 w-4" /></Button>
            </li>
          ))}
        </ul>
      )}
      <Button size="sm" variant="outline" onClick={() => setEditing('new')}><Plus className="mr-1 h-4 w-4" />Add a rule</Button>
      <TestBox gateway={gw} />
      {editing && (
        <BindingDialog
          gateway={gw}
          provider={gateway.provider}
          rule={editing === 'new' ? null : editing}
          agents={agents}
          flows={flows}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void load(); }}
        />
      )}
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this rule?</AlertDialogTitle>
            <AlertDialogDescription>Messages it matched will fall through to the next rule or the default.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

for (const provider of PROVIDERS) {
  registerProviderPanel(provider, { id: 'routing-rules', title: 'Routing rules', component: BindingsPanel });
}
