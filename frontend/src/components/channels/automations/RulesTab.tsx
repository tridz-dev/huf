import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, Loader2, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getRules, saveRules, type RoutingRule, type RuleTargetType, type RuleType } from '@/services/channels/channelsRulesApi';
import { move, newRule, renumber, RULE_TYPES, TARGET_TYPES, validateRules } from './rulesModel';

export interface TargetOption { value: string; label: string }
export interface RulesTabProps {
  gw: string;
  solutions: TargetOption[];
  agents: TargetOption[];
}

export function RulesTab({ gw, solutions, agents }: RulesTabProps) {
  const [rules, setRules] = useState<RoutingRule[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setRules(null);
    getRules(gw).then((r) => live && setRules([...r].sort((a, b) => a.priority - b.priority)))
      .catch((e) => live && setError(getFrappeErrorMessage(e)));
    return () => { live = false; };
  }, [gw]);

  if (!rules) return error ? <p role="alert" className="text-sm text-destructive">{error}</p> : <p className="text-sm text-steel">Loading...</p>;

  const patch = (i: number, p: Partial<RoutingRule>) => setRules(rules.map((r, k) => (k === i ? { ...r, ...p } : r)));
  const submit = async () => {
    const err = validateRules(rules);
    if (err) { setError(err); return; }
    setError('');
    setBusy(true);
    try {
      const saved = await saveRules(gw, renumber(rules));
      setRules([...saved].sort((a, b) => a.priority - b.priority));
      toast.success('Routing rules saved');
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };
  const options = (t: RuleTargetType) => (t === 'solution' ? solutions : t === 'agent' ? agents : []);

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Routing rules</CardTitle></CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-xs text-steel">Rules run top to bottom; the first match answers. Use a keyword rule with target Human to hand a chat to a person.</p>
        {rules.length === 0 && <p className="text-sm text-steel">No rules yet.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-steel">
                <th className="pb-1 pr-2 font-medium">#</th><th className="pb-1 pr-2 font-medium">Type</th>
                <th className="pb-1 pr-2 font-medium">Match</th><th className="pb-1 pr-2 font-medium">Attribute</th>
                <th className="pb-1 pr-2 font-medium">Goes to</th><th className="pb-1 pr-2 font-medium">Target</th>
                <th className="pb-1 pr-2 font-medium">On</th><th className="pb-1 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r, i) => (
                <tr key={i} className="align-middle">
                  <td className="py-1 pr-2 text-steel">{i + 1}</td>
                  <td className="py-1 pr-2">
                    <Select value={r.rule_type} onValueChange={(v) => patch(i, { rule_type: v as RuleType })}>
                      <SelectTrigger aria-label={`Rule ${i + 1} type`} size="sm" className="w-40"><SelectValue /></SelectTrigger>
                      <SelectContent>{RULE_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="py-1 pr-2"><Input aria-label={`Rule ${i + 1} match`} size="sm" value={r.match_value ?? ''} disabled={r.rule_type === 'fallback'} onChange={(e) => patch(i, { match_value: e.target.value })} /></td>
                  <td className="py-1 pr-2"><Input aria-label={`Rule ${i + 1} attribute`} size="sm" value={r.attribute ?? ''} disabled={r.rule_type !== 'contact_attribute'} onChange={(e) => patch(i, { attribute: e.target.value })} /></td>
                  <td className="py-1 pr-2">
                    <Select value={r.target_type} onValueChange={(v) => patch(i, { target_type: v as RuleTargetType, target: '' })}>
                      <SelectTrigger aria-label={`Rule ${i + 1} target type`} size="sm" className="w-32"><SelectValue /></SelectTrigger>
                      <SelectContent>{TARGET_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="py-1 pr-2">
                    {r.target_type === 'human' ? <span className="text-xs text-steel">A person</span> : (
                      <Select value={r.target || undefined} onValueChange={(v) => patch(i, { target: v })}>
                        <SelectTrigger aria-label={`Rule ${i + 1} target`} size="sm" className="w-48"><SelectValue placeholder="Choose..." /></SelectTrigger>
                        <SelectContent>{options(r.target_type).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                      </Select>
                    )}
                  </td>
                  <td className="py-1 pr-2"><Switch aria-label={`Rule ${i + 1} enabled`} checked={!!r.enabled} onCheckedChange={(c) => patch(i, { enabled: c ? 1 : 0 })} /></td>
                  <td className="whitespace-nowrap py-1">
                    <Button variant="ghost" size="icon" aria-label={`Move rule ${i + 1} up`} disabled={i === 0} onClick={() => setRules(move(rules, i, -1))}><ArrowUp className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" aria-label={`Move rule ${i + 1} down`} disabled={i === rules.length - 1} onClick={() => setRules(move(rules, i, 1))}><ArrowDown className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" aria-label={`Delete rule ${i + 1}`} onClick={() => setRules(rules.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setRules([...rules, newRule()])}><Plus className="h-4 w-4" />Add rule</Button>
          <Button onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}
