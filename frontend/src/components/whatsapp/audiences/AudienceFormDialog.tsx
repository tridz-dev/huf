import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { errorText } from '@/services/whatsappApi';
import {
  CONSENT_BASES, CONSENT_PURPOSES, createAudience, updateAudience,
  type Audience, type ConsentBasis, type ConsentPurpose,
} from './audiencesApi';

interface Props { gateway: string; audience?: Audience | null; onClose: () => void; onSaved: (a: Audience) => void }

export function AudienceFormDialog({ gateway, audience, onClose, onSaved }: Props) {
  const editing = Boolean(audience);
  const [title, setTitle] = useState(audience?.title ?? '');
  const [description, setDescription] = useState(audience?.description ?? '');
  const [source, setSource] = useState(audience?.consent_source ?? '');
  const [basis, setBasis] = useState<ConsentBasis | ''>(audience?.consent_basis ?? '');
  const [purposes, setPurposes] = useState<ConsentPurpose[]>(audience?.consent_purposes ?? []);
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const togglePurpose = (p: ConsentPurpose, on: boolean) =>
    setPurposes((cur) => (on ? [...cur, p] : cur.filter((x) => x !== p)));
  const missing = !title.trim() ? 'Enter a name for this audience.'
    : !source.trim() ? 'Say where these contacts agreed to hear from you.'
    : !basis ? 'Choose how these contacts agreed.'
    : purposes.length === 0 ? 'Choose at least one kind of message they agreed to.'
    : !editing && !attested ? 'Confirm that these contacts agreed to receive your messages.' : '';

  const save = async () => {
    if (missing) { setErr(missing); return; }
    setBusy(true); setErr('');
    const body = { title: title.trim(), description: description.trim(), consent_source: source.trim(), consent_purposes: purposes };
    const res = editing && audience
      ? await updateAudience(audience.name, body)
      : await createAudience({ gateway, ...body, consent_basis: basis as ConsentBasis, consent_attested: true });
    setBusy(false);
    if (!res.success) { setErr(errorText(res)); return; }
    toast.success(editing ? 'Audience updated' : 'Audience created');
    onSaved(res.audience);
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit audience' : 'New audience'}</DialogTitle>
          <DialogDescription>
            An audience is a list of contacts who agreed to hear from you. Record how they agreed, so every broadcast to this list is covered.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="Name" id="aud-title" required>
            <Input id="aud-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Description (optional)" id="aud-desc">
            <Textarea id="aud-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label="Where did they agree?" id="aud-source" required hint="For example: Website signup form, Spring sale checkout, In-store sheet">
            <Input id="aud-source" value={source} onChange={(e) => setSource(e.target.value)} />
          </Field>
          <Field label="How did they agree?" id="aud-basis" required>
            {(p) => (
              <Select value={basis || undefined} disabled={editing} onValueChange={(v) => setBasis(v as ConsentBasis)}>
                <SelectTrigger {...p} className="w-full" aria-label="How did they agree?">
                  <SelectValue placeholder="Choose one" />
                </SelectTrigger>
                <SelectContent>
                  {CONSENT_BASES.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </Field>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">What did they agree to receive?</legend>
            {CONSENT_PURPOSES.map((p) => (
              <div key={p.value} className="flex items-center gap-2">
                <Checkbox
                  id={`aud-purpose-${p.value}`}
                  checked={purposes.includes(p.value)}
                  disabled={editing && !audience?.consent_purposes.includes(p.value)}
                  onCheckedChange={(c) => togglePurpose(p.value, c === true)}
                />
                <Label htmlFor={`aud-purpose-${p.value}`} className="text-sm font-normal">{p.label}</Label>
              </div>
            ))}
            {editing && <p className="text-xs text-steel">You can narrow what they agreed to, but not add to it.</p>}
            <p className="text-xs text-steel">Marketing templates can only be sent to audiences that agreed to marketing.</p>
          </fieldset>
          {editing ? (
            <p className="text-xs text-steel">
              Confirmed{audience?.consent_attested_by ? ` by ${audience.consent_attested_by}` : ''}
              {audience?.consent_attested_at ? ` on ${audience.consent_attested_at}` : ''}. This cannot be changed.
            </p>
          ) : (
            <div className="flex items-start gap-2">
              <Checkbox id="aud-attest" checked={attested} onCheckedChange={(c) => setAttested(c === true)} />
              <Label htmlFor="aud-attest" className="text-sm font-normal">
                I confirm everyone I add to this audience agreed to receive these messages from my business.
              </Label>
            </div>
          )}
          {err && <p role="alert" className="text-sm text-destructive">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={busy} onClick={() => void save()}>{editing ? 'Save changes' : 'Create audience'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
