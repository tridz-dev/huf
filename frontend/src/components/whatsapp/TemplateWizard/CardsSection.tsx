import { useRef, useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, Loader2, Plus, Reply, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { errorText, uploadPublicFile } from '@/services/whatsappApi';
import { cardButtonBlocker } from '../template/cards';
import type { TemplateWizardDraft, WizardButton, WizardCard } from '../template/draft';
import { WIZARD_LIMITS } from '../template/rules';
import { extractVariables } from '../template/variables';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';

export interface CardActions {
  onAdd: () => void;
  onRemove: (card: number) => void;
  onMove: (card: number, by: -1 | 1) => void;
  onCard: (card: number, patch: Partial<WizardCard>) => void;
  onAddButton: (type: 'QUICK_REPLY' | 'URL') => void;
  onRemoveButton: (button: number) => void;
  onButton: (card: number, button: number, patch: Partial<WizardButton>) => void;
}

interface Props extends CardActions {
  draft: TemplateWizardDraft;
  field: FieldApi;
}

function CardMedia({ card, index, field, onCard }: { card: WizardCard; index: number; field: FieldApi; onCard: CardActions['onCard'] }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const path = `cards.${index}.mediaSample`;
  const error = field.error(path);
  const id = `tpl-card-${index}-media`;
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    const res = await uploadPublicFile(file);
    setUploading(false);
    if ('fileUrl' in res) {
      onCard(index, { mediaSample: res.fileUrl });
      field.touch(path);
    } else toast.error(errorText(res));
  };
  return (
    <div className="space-y-2">
      <ToggleGroup
        type="single"
        variant="outline"
        aria-label={`Card ${index + 1} media type`}
        value={card.headerType}
        onValueChange={(v) => v && onCard(index, { headerType: v as WizardCard['headerType'] })}
      >
        <ToggleGroupItem value="image">Image</ToggleGroupItem>
        <ToggleGroupItem value="video">Video</ToggleGroupItem>
      </ToggleGroup>
      <Field id={id} label="Sample file" error={error} hint="A public https link or an upload. Every card uses the same media type.">
        <div className="flex gap-2">
          <Input
            {...controlA11y(id, error)}
            value={card.mediaSample}
            placeholder="https://example.com/card.png"
            onChange={(e) => onCard(index, { mediaSample: e.target.value })}
            onBlur={() => field.touch(path)}
          />
          <Button type="button" variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Upload className="mr-1.5 h-4 w-4" aria-hidden />}
            Upload
          </Button>
          <input
            ref={fileRef}
            type="file"
            hidden
            aria-label={`Upload card ${index + 1} sample file`}
            accept={card.headerType === 'video' ? 'video/mp4' : 'image/jpeg,image/png'}
            onChange={(e) => {
              void upload(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
        </div>
      </Field>
    </div>
  );
}

function CardBody({ card, index, field, onCard }: { card: WizardCard; index: number; field: FieldApi; onCard: CardActions['onCard'] }) {
  const path = `cards.${index}.body`;
  const id = `tpl-card-${index}-body`;
  const error = field.error(path);
  const tokens = extractVariables(card.body, 'number');
  return (
    <>
      <Field id={id} label="Card text" error={error} hint="Numbered variables like {{1}} are allowed." counter={{ length: card.body.length, max: WIZARD_LIMITS.cardBody }}>
        <Textarea {...controlA11y(id, error)} rows={3} value={card.body} onChange={(e) => onCard(index, { body: e.target.value })} onBlur={() => field.touch(path)} />
      </Field>
      {tokens.map((t) => {
        const sp = `cards.${index}.samples.${t}`;
        const sid = `tpl-card-${index}-sample-${t}`;
        const serr = field.error(sp);
        const n = Number(t) - 1;
        return (
          <Field key={t} id={sid} label={`Example for {{${t}}}`} error={serr}>
            <Input
              {...controlA11y(sid, serr)}
              value={card.samples[n] ?? ''}
              onChange={(e) => {
                const samples = [...card.samples];
                samples[n] = e.target.value;
                onCard(index, { samples: Array.from(samples, (v) => v ?? '') });
              }}
              onBlur={() => field.touch(sp)}
            />
          </Field>
        );
      })}
    </>
  );
}

function CardButton({ b, card, j, field, onButton }: { b: WizardButton; card: number; j: number; field: FieldApi; onButton: CardActions['onButton'] }) {
  const input = (name: 'text' | 'url' | 'urlExample', label: string, placeholder: string) => {
    const path = `cards.${card}.buttons.${j}.${name}`;
    const id = `tpl-card-${card}-btn-${j}-${name}`;
    const error = field.error(path);
    return (
      <Field id={id} label={label} error={error}>
        <Input {...controlA11y(id, error)} value={b[name]} placeholder={placeholder} onChange={(e) => onButton(card, j, { [name]: e.target.value })} onBlur={() => field.touch(path)} />
      </Field>
    );
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2" role="group" aria-label={`Card ${card + 1} button ${j + 1}`}>
      {input('text', b.type === 'URL' ? 'Website button text' : 'Reply button text', 'Shop now')}
      {b.type === 'URL' && input('url', 'Website link', 'https://example.com/item/{{1}}')}
      {b.type === 'URL' && b.url.includes('{{') && input('urlExample', 'Example link', 'https://example.com/item/123')}
    </div>
  );
}

export function CardsSection({ draft, field, onAdd, onRemove, onMove, onCard, onAddButton, onRemoveButton, onButton }: Props) {
  const n = draft.cards.length;
  const groupError = field.error('cards');
  const shape = draft.cards[0]?.buttons ?? [];
  return (
    <Section title="Cards" description={`${WIZARD_LIMITS.cardsMin} to ${WIZARD_LIMITS.cardsMax} cards. Each has one image or video, some text and the same buttons.`}>
      <div className="space-y-2 rounded-md border border-line p-3">
        <p className="text-xs font-medium text-ink">Buttons on every card (up to {WIZARD_LIMITS.cardButtons})</p>
        <div className="flex flex-wrap items-center gap-2">
          {shape.map((b, j) => (
            <span key={b.id} className="inline-flex items-center gap-1.5 rounded-md bg-paper-deep px-2 py-1 text-xs">
              {b.type === 'URL' ? <ExternalLink className="h-3.5 w-3.5" aria-hidden /> : <Reply className="h-3.5 w-3.5" aria-hidden />}
              {b.type === 'URL' ? 'Website' : 'Reply'} {j + 1}
              <Button type="button" variant="ghost" size="icon" className="h-5 w-5" aria-label={`Remove button ${j + 1} from every card`} onClick={() => onRemoveButton(j)}>
                <Trash2 className="h-3 w-3" aria-hidden />
              </Button>
            </span>
          ))}
          <Button type="button" variant="outline" size="sm" disabled={!!cardButtonBlocker(draft, 'QUICK_REPLY')} onClick={() => onAddButton('QUICK_REPLY')}>
            <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Reply button
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={!!cardButtonBlocker(draft, 'URL')} onClick={() => onAddButton('URL')}>
            <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Website button
          </Button>
        </div>
      </div>

      {draft.cards.map((c, i) => (
        <div key={c.id} className="space-y-3 rounded-md border border-line p-3" role="group" aria-label={`Card ${i + 1}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-ink">Card {i + 1}</span>
            <span className="flex items-center">
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" disabled={i === 0} aria-label={`Move card ${i + 1} up`} onClick={() => onMove(i, -1)}>
                <ChevronUp className="h-4 w-4" aria-hidden />
              </Button>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" disabled={i === n - 1} aria-label={`Move card ${i + 1} down`} onClick={() => onMove(i, 1)}>
                <ChevronDown className="h-4 w-4" aria-hidden />
              </Button>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" disabled={n <= WIZARD_LIMITS.cardsMin} aria-label={`Remove card ${i + 1}`} onClick={() => onRemove(i)}>
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </span>
          </div>
          <CardMedia card={c} index={i} field={field} onCard={onCard} />
          <CardBody card={c} index={i} field={field} onCard={onCard} />
          {c.buttons.map((b, j) => (
            <CardButton key={b.id} b={b} card={i} j={j} field={field} onButton={onButton} />
          ))}
          {field.error(`cards.${i}.buttons`) && <p role="alert" className="text-[11px] text-destructive">{field.error(`cards.${i}.buttons`)}</p>}
        </div>
      ))}

      <div className="flex items-center justify-between gap-3">
        <Button type="button" variant="outline" size="sm" disabled={n >= WIZARD_LIMITS.cardsMax} onClick={onAdd}>
          <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Add card
        </Button>
        <span className="text-[11px] text-steel">{n}/{WIZARD_LIMITS.cardsMax}</span>
      </div>
      {groupError && <p role="alert" className="text-[11px] text-destructive">{groupError}</p>}
    </Section>
  );
}
