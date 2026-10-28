import { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { errorText } from '@/services/whatsappApi';
import {
  getAudience, listAudiences, previewAudienceSelection,
  type Audience, type AudienceSelectionItem, type SelectionPreview,
} from './audiencesApi';

interface Props {
  gateway: string;
  value: AudienceSelectionItem[];
  onChange: (next: AudienceSelectionItem[]) => void;
  /**
   * Broadcast used for exact counts (duplicates, opt-outs, purpose check). Without one (before the broadcast
   * exists) the counts are an estimate from audience sizes.
   */
  broadcast?: string;
  onPreview?: (p: SelectionPreview | null) => void;
}

/** Reusable multi-select: pick audiences, narrow each by tag, include or exclude, see live counts. */
export function AudiencePicker({ gateway, value, onChange, broadcast, onPreview }: Props) {
  const [audiences, setAudiences] = useState<Audience[]>([]);
  const [tagsByAudience, setTags] = useState<Record<string, string[]>>({});
  const [preview, setPreview] = useState<SelectionPreview | null>(null);
  const [error, setError] = useState('');
  const [adding, setAdding] = useState('');
  const seq = useRef(0);

  useEffect(() => {
    void listAudiences(gateway).then((r) => { if (r.success) setAudiences(r.audiences); else setError(errorText(r)); });
  }, [gateway]);

  const key = JSON.stringify(value);
  useEffect(() => {
    const id = ++seq.current;
    if (!value.length) { setPreview(null); onPreview?.(null); return; }
    if (!broadcast) {
      // No broadcast yet: the server preview needs one, so estimate from the audience sizes.
      if (!audiences.length) return;
      const est = estimate(value, audiences);
      setPreview(est); setError(''); onPreview?.(est);
      return;
    }
    void previewAudienceSelection(broadcast, value).then((r) => {
      if (id !== seq.current) return;
      if (r.success) { setPreview(r); setError(''); onPreview?.(r); } else { setError(errorText(r)); onPreview?.(null); }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, broadcast, audiences]);

  useEffect(() => {
    for (const v of value) {
      if (tagsByAudience[v.audience]) continue;
      setTags((t) => ({ ...t, [v.audience]: [] }));
      void getAudience(v.audience).then((r) => { if (r.success) setTags((t) => ({ ...t, [v.audience]: r.audience.tags.map((x) => x.tag) })); });
    }
  }, [key, tagsByAudience, value]);

  const patch = (i: number, p: Partial<AudienceSelectionItem>) => onChange(value.map((v, n) => (n === i ? { ...v, ...p } : v)));
  const title = (id: string) => audiences.find((a) => a.name === id)?.title ?? id;
  const available = audiences.filter((a) => !value.some((v) => v.audience === a.name));

  return (
    <div className="space-y-3">
      <Field label="Add an audience" id="aud-pick">
        {(p) => (
          <Select value={adding || undefined} onValueChange={(v) => { setAdding(''); onChange([...value, { audience: v, tags: [], tag_filter_mode: 'any', exclude: false }]); }}>
            <SelectTrigger {...p} className="w-full" aria-label="Add an audience"><SelectValue placeholder="Choose an audience" /></SelectTrigger>
            <SelectContent>
              {available.map((a) => <SelectItem key={a.name} value={a.name}>{a.title} ({a.member_count})</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </Field>
      {value.map((v, i) => (
        <div key={v.audience} className="rounded-md border p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium">{title(v.audience)}</span>
            <div className="flex items-center gap-3 text-xs">
              <div className="flex items-center gap-1">
                <Checkbox
                  aria-label={`Exclude ${title(v.audience)}`}
                  checked={Boolean(v.exclude)}
                  onCheckedChange={(c) => patch(i, { exclude: c === true })}
                />
                Exclude these contacts
              </div>
              <Button variant="ghost" size="sm" onClick={() => onChange(value.filter((_, n) => n !== i))}>Remove</Button>
            </div>
          </div>
          {(tagsByAudience[v.audience] ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label={`Tags for ${title(v.audience)}`}>
              {tagsByAudience[v.audience].map((t) => {
                const on = v.tags?.includes(t);
                return (
                  <Button
                    key={t}
                    size="sm"
                    variant={on ? 'default' : 'outline'}
                    aria-pressed={on}
                    onClick={() => patch(i, { tags: on ? (v.tags ?? []).filter((x) => x !== t) : [...(v.tags ?? []), t] })}
                  >
                    {t}
                  </Button>
                );
              })}
            </div>
          )}
          {preview?.blocked.filter((b) => b.audience === v.audience).map((b) => (
            <p key={b.code} role="alert" className="mt-2 text-xs text-destructive">{b.message}</p>
          ))}
        </div>
      ))}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {preview && (
        <>
          <div className="flex flex-wrap gap-2 text-xs" role="status" aria-label="Audience counts">
            <Badge variant="secondary">{preview.estimated ? 'Up to ' : ''}Selected {preview.counts.total}</Badge>
            {!preview.estimated && <Badge variant="secondary">Excluded {preview.counts.excluded}</Badge>}
            {!preview.estimated && <Badge variant="secondary">Duplicates {preview.counts.dupes}</Badge>}
            <Badge variant="secondary">Opted out {preview.counts.suppressed}</Badge>
            {preview.counts.blocked_by_purpose > 0 && (
              <Badge variant="destructive">Not agreed to this message type {preview.counts.blocked_by_purpose}</Badge>
            )}
            <Badge>{preview.estimated ? 'About ' : ''}Will receive {preview.counts.final}</Badge>
          </div>
          {preview.estimated && (
            <p className="text-xs text-steel">
              Estimate from audience sizes. Duplicates between lists, exclusions and message-type checks are counted once the broadcast is created.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Rough counts from member_count / suppressed_count when no broadcast exists to preview against. */
function estimate(value: AudienceSelectionItem[], audiences: Audience[]): SelectionPreview {
  const sum = (pick: (a: Audience) => number) =>
    value.reduce((n, v) => (v.exclude ? n : n + pick(audiences.find((a) => a.name === v.audience) ?? ({} as Audience))), 0);
  const total = sum((a) => a.member_count || 0);
  const suppressed = sum((a) => a.suppressed_count || 0);
  return {
    counts: { total, dupes: 0, excluded: 0, suppressed, blocked_by_purpose: 0, final: Math.max(total - suppressed, 0) },
    per_audience: [], blocked: [], estimated: true,
  };
}
