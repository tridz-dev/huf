import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { TemplatePreview } from '../TemplatePreview';
import { isSelectableKind, kindById, TEMPLATE_KINDS, type TemplateKind } from '../template/catalogue';
import type { TemplateCategoryId } from '../template/draft';
import { StepLayout } from './fields';

const META_LIBRARY_URL = 'https://business.facebook.com/latest/whatsapp_manager/message_templates';

interface Props {
  kindId: string;
  onSelect: (kind: TemplateKind) => void;
}

const kindsFor = (tab: TemplateCategoryId) =>
  TEMPLATE_KINDS.filter((k) => k.category === tab || (tab === 'MARKETING' && k.availability === 'comingSoon'));

export function TypeStep({ kindId, onSelect }: Props) {
  const selected = kindById(kindId);
  const [tab, setTab] = useState<TemplateCategoryId>(selected?.category ?? 'MARKETING');
  const kinds = kindsFor(tab);
  const previewed = selected && kinds.includes(selected) ? selected : kinds[0];
  const auth = kindById('authentication');

  return (
    <StepLayout
      aside={
        <>
          <TemplatePreview sample={previewed.id === 'utility_default' ? 'utility_default' : 'marketing_default'} time="10:30" />
          <div className="space-y-3 rounded-md border border-line bg-panel p-4">
            <div>
              <h3 className="text-sm font-semibold text-ink">Good for</h3>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-steel">
                {previewed.goodFor.map((g) => <li key={g}>{g}</li>)}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-ink">Parts you can change</h3>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {previewed.customisable.map((c) => <li key={c}><Badge variant="pill-neutral" size="sm">{c}</Badge></li>)}
              </ul>
            </div>
          </div>
        </>
      }
    >
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">What kind of message is it?</h2>
        <p className="text-sm text-steel">WhatsApp reviews and prices templates by type. Choose the one that fits.</p>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TemplateCategoryId)}>
        <TabsList>
          <TabsTrigger value="MARKETING">Marketing</TabsTrigger>
          <TabsTrigger value="UTILITY">Utility</TabsTrigger>
          <TabsTrigger value="AUTHENTICATION" disabled title={auth?.disabledReason} aria-describedby="auth-reason">Authentication</TabsTrigger>
        </TabsList>
      </Tabs>
      {auth?.disabledReason && <span id="auth-reason" className="sr-only">Authentication: {auth.disabledReason}</span>}

      <RadioGroup
        aria-label="Template type"
        value={kindId}
        onValueChange={(id) => {
          const kind = kindById(id);
          if (kind && isSelectableKind(kind)) onSelect(kind);
        }}
      >
        {kinds.map((k) => {
          const enabled = isSelectableKind(k);
          return (
            <label
              key={k.id}
              htmlFor={`kind-${k.id}`}
              className={cn(
                'flex items-start gap-3 rounded-md border bg-panel p-3',
                enabled ? 'cursor-pointer hover:bg-paper-deep' : 'cursor-not-allowed opacity-60',
                kindId === k.id ? 'border-ink' : 'border-line',
              )}
            >
              <RadioGroupItem id={`kind-${k.id}`} value={k.id} disabled={!enabled} className="mt-0.5" aria-describedby={`kind-${k.id}-desc`} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                  {k.title} <span className="font-normal text-steel">{k.subtype}</span>
                  {k.availability === 'comingSoon' && <Badge variant="pill-neutral" size="sm">Coming soon</Badge>}
                </span>
                <span id={`kind-${k.id}-desc`} className="block text-xs text-steel">{k.description}</span>
              </span>
            </label>
          );
        })}
      </RadioGroup>

      <a
        href={META_LIBRARY_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-signal-ink underline-offset-2 hover:underline"
      >
        Start from Meta's template library <ExternalLink className="h-3 w-3" aria-hidden />
      </a>
    </StepLayout>
  );
}
