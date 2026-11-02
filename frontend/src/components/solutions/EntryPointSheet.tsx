import { useEffect, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { SolutionsApiError, deleteEntryPoint, saveEntryPoint } from '@/services/solutionsApi';
import type { EntryMatchType, EntryPoint, RunsOn } from '@/types/solutions';

/** Plain-language rule, e.g. "Message contains refund". */
export function describeRule(e: EntryPoint): ReactNode {
  const values = (e.match_values ?? []).map((v, i) => (
    <span key={v}>
      {i > 0 ? ' or ' : ''}
      <b>{v}</b>
    </span>
  ));
  switch (e.match_type) {
    case 'Keyword':
      return <>Message contains {values}</>;
    case 'Ad or link tag':
      return <>Ad or link tag is {values}</>;
    case 'Catch-all':
      return <>Any message nobody else claims</>;
    default:
      return <>{e.match_type}{values.length ? <> : {values}</> : null}</>;
  }
}

export interface Ceiling {
  value: number | null;
  source: EntryPoint['ceiling_source'];
}

interface EntryPointSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  solution: string;
  /** null = create mode. */
  entry: EntryPoint | null;
  gateways: RunsOn[];
  /** The number's recipient scope (limits.scope), used to offer only narrower scopes. */
  gatewayScope: string | null;
  ceilingFor: (gateway: string) => Ceiling;
  onSaved: () => void;
}

const nativeSelect =
  'h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** Widest to narrowest. A binding may only be equal to or narrower than its number. */
const SCOPE_RANK: Record<string, number> = {
  'Any number': 3,
  'Only approved contacts': 2,
  'Approved contacts': 2,
  'Allow list': 1,
  'Allow-list': 1,
  'Current contact': 0,
};
const OVERRIDE_OPTIONS = ['Only approved contacts', 'Allow list'];

export function scopeOptions(gatewayScope: string | null): string[] {
  const limit = gatewayScope ? SCOPE_RANK[gatewayScope] : undefined;
  if (limit === undefined) return OVERRIDE_OPTIONS;
  return OVERRIDE_OPTIONS.filter((s) => SCOPE_RANK[s] <= limit);
}

const CREATE_TYPES: Array<{ value: EntryMatchType; label: string; hint: string }> = [
  { value: 'Keyword', label: 'Keyword', hint: 'Comma-separated words, e.g. order, menu' },
  { value: 'Ad or link tag', label: 'Ad or link tag', hint: 'The tag from your ad or link, e.g. spring-promo' },
  { value: 'Catch-all', label: 'Catch-all', hint: 'Takes every message nobody else claims.' },
];

const ERROR_COPY: Record<string, string> = {
  cap_exceeds_ceiling: 'That is above this number\'s daily limit.',
  scope_loosening: 'An entry point can only be as wide as its number, or narrower.',
};

export function EntryPointSheet({ open, onOpenChange, solution, entry, gateways, gatewayScope, ceilingFor, onSaved }: EntryPointSheetProps) {
  const creating = entry === null;
  const [gateway, setGateway] = useState('');
  const [matchType, setMatchType] = useState<EntryMatchType>('Keyword');
  const [valuesText, setValuesText] = useState('');
  const [cap, setCap] = useState(0);
  const [scope, setScope] = useState('');
  const [first, setFirst] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    const gw = entry?.gateway ?? gateways[0]?.gateway ?? '';
    const c = ceilingFor(gw).value;
    setGateway(gw);
    setMatchType(entry?.match_type ?? 'Keyword');
    setValuesText(entry?.match_values.join(', ') ?? '');
    setCap(entry?.cap_per_day ?? c ?? 100);
    setScope(entry?.scope_override ?? '');
    setFirst(entry?.allow_first_message ?? false);
    setError(null);
    setConfirmDelete(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, entry]);

  const ceiling = ceilingFor(gateway);
  const numberLabel = gateways.find((g) => g.gateway === gateway)?.label ?? gateway;
  const locked = ceiling.source !== 'none' && ceiling.value !== null;
  const options = scopeOptions(gatewayScope);
  const typeHint = CREATE_TYPES.find((t) => t.value === matchType)?.hint ?? '';

  const fail = (err: unknown) => {
    if (err instanceof SolutionsApiError) setError({ code: err.code, message: err.message });
    else setError({ code: 'unknown', message: err instanceof Error ? err.message : 'Something went wrong.' });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const values = valuesText.split(',').map((v) => v.trim()).filter(Boolean);
      await saveEntryPoint(solution, {
        ...(entry ? { name: entry.name } : {}),
        gateway,
        ...(creating ? { match_type: matchType, match_values: matchType === 'Catch-all' ? [] : values } : {}),
        cap_per_day: cap,
        scope_override: scope || null,
        allow_first_message: first,
      });
      onSaved();
      onOpenChange(false);
    } catch (err) {
      fail(err);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!entry) return;
    setSaving(true);
    try {
      await deleteEntryPoint(entry.name);
      setConfirmDelete(false);
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setConfirmDelete(false);
      fail(err);
    } finally {
      setSaving(false);
    }
  };

  const needsValues = matchType !== 'Catch-all';
  const canSave = !saving && !!gateway && (!creating || !needsValues || valuesText.trim().length > 0);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{creating ? 'Add entry point' : 'Entry point'}</SheetTitle>
          <SheetDescription>
            {creating ? 'Choose what sends a customer message to this solution.' : describeRule(entry)}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-4 text-sm">
          {creating ? (
            <>
              {gateways.length > 1 ? (
                <div className="space-y-1">
                  <label htmlFor="ep-number" className="font-medium">Number</label>
                  <select id="ep-number" className={nativeSelect} value={gateway} onChange={(e) => setGateway(e.target.value)}>
                    {gateways.map((g) => <option key={g.gateway} value={g.gateway}>{g.label}</option>)}
                  </select>
                </div>
              ) : null}
              <div className="space-y-1">
                <label htmlFor="ep-type" className="font-medium">Match type</label>
                <select id="ep-type" className={nativeSelect} value={matchType} onChange={(e) => setMatchType(e.target.value as EntryMatchType)}>
                  {CREATE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              {needsValues ? (
                <div className="space-y-1">
                  <label htmlFor="ep-values" className="font-medium">Values</label>
                  <Input id="ep-values" value={valuesText} onChange={(e) => setValuesText(e.target.value)} />
                  <p className="text-xs text-steel">{typeHint}</p>
                </div>
              ) : (
                <p className="text-xs text-steel">{typeHint}</p>
              )}
            </>
          ) : null}

          <div className="space-y-2">
            <label htmlFor="ep-cap" className="font-medium">Daily messages it may start</label>
            <div className="flex items-center gap-3">
              {locked ? (
                <Slider
                  aria-label="Daily messages it may start"
                  min={0}
                  max={ceiling.value as number}
                  step={1}
                  value={[Math.min(cap, ceiling.value as number)]}
                  onValueChange={(v) => setCap(v[0] ?? 0)}
                />
              ) : null}
              <Input
                id="ep-cap"
                type="number"
                min={0}
                {...(locked ? { max: ceiling.value as number } : {})}
                className="w-24 shrink-0"
                value={cap}
                onChange={(e) => setCap(Math.max(0, Number(e.target.value) || 0))}
              />
            </div>
            {locked ? (
              <p className="text-xs text-steel">Maximum {ceiling.value}, set on {numberLabel}</p>
            ) : (
              <p className="text-xs text-steel">No limit is set on this number, so there is no maximum. Pick a cap that suits this entry point.</p>
            )}
          </div>

          <div className="space-y-1">
            <label htmlFor="ep-scope" className="font-medium">Who it may message</label>
            <select id="ep-scope" className={nativeSelect} value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="">Same as the number{gatewayScope ? ` (${gatewayScope})` : ''}</option>
              {options.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <p className="text-xs text-steel">You can only make this narrower than the number, never wider.</p>
          </div>

          <label className="flex items-start gap-2">
            <Checkbox checked={first} onCheckedChange={(v) => setFirst(v === true)} aria-label="May message customers first (templates only)" />
            <span>May message customers first (templates only)</span>
          </label>

          {error ? (
            <div role="alert" data-code={error.code} className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-ink">
              {ERROR_COPY[error.code] ? <p className="font-medium">{ERROR_COPY[error.code]}</p> : null}
              <p>{error.message}</p>
            </div>
          ) : null}
        </div>

        <SheetFooter className="mt-auto gap-2 sm:justify-between">
          {!creating ? (
            <Button variant="outline" onClick={() => setConfirmDelete(true)} disabled={saving}>Delete entry point</Button>
          ) : <span />}
          <Button onClick={save} disabled={!canSave}>Save</Button>
        </SheetFooter>

        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete this entry point?</AlertDialogTitle>
              <AlertDialogDescription>Messages that matched it will be routed by your other rules.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it</AlertDialogCancel>
              <AlertDialogAction onClick={(e) => { e.preventDefault(); void remove(); }}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SheetContent>
    </Sheet>
  );
}
