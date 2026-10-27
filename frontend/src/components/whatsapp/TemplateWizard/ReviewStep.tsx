import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { TemplatePreview } from '../TemplatePreview';
import type { TemplateWizardDraft } from '../template/draft';
import { localeLabel } from '../template/locales';
import { validateDraft } from '../template/rules';
import { draftToPreviewModel } from './previewModel';
import { sampleVariables, ttlLabel } from './draftActions';
import { StepLayout } from './fields';

const BUTTON_LABEL = { QUICK_REPLY: 'Custom reply', URL: 'Website', PHONE_NUMBER: 'Phone', COPY_CODE: 'Offer code' } as const;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 py-2 sm:grid-cols-[140px_minmax(0,1fr)] sm:gap-3">
      <dt className="text-xs text-steel">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-ink">{children}</dd>
    </div>
  );
}

function headerSummary(draft: TemplateWizardDraft): string {
  const { header } = draft;
  if (header.type === 'none') return 'None';
  if (header.type === 'text') return header.text;
  if (header.type === 'location') return 'Location';
  return `${header.type[0].toUpperCase()}${header.type.slice(1)}: ${header.mediaSample}`;
}

interface Props {
  draft: TemplateWizardDraft;
  /** Heading of the kind picked in step 1, e.g. "Marketing · Default". */
  kindLabel: string;
  isEdit: boolean;
  /** True when the final action sends the template to WhatsApp right away. */
  direct: boolean;
  /** Replaces the default line under the heading, e.g. when an admin reviews a request. */
  intro?: string;
}

export function ReviewStep({ draft, kindLabel, isEdit, direct, intro }: Props) {
  const samples = sampleVariables(draft);
  const issues = Object.values(validateDraft(draft));
  return (
    <StepLayout aside={<TemplatePreview model={draftToPreviewModel(draft)} />}>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">Check and send</h2>
        <p className="text-sm text-steel">
          {intro ?? (isEdit ? 'Review your changes. WhatsApp reviews them again.' : direct ? 'Review the template, then send it to WhatsApp.' : 'Review the template, then ask an admin to approve it.')}
        </p>
      </div>

      <dl className="divide-y divide-line rounded-md border border-line bg-panel px-4">
        <Row label="Type">{kindLabel}</Row>
        <Row label="Name">
          <span className="font-mono">{draft.name}</span> · {localeLabel(draft.language)}
        </Row>
        <Row label="Header">{headerSummary(draft)}</Row>
        <Row label="Body"><span className="whitespace-pre-wrap">{draft.body}</span></Row>
        <Row label="Footer">{draft.footer.trim() || 'None'}</Row>
        <Row label="Buttons">
          {draft.buttons.length === 0 ? 'None' : (
            <ul className="space-y-0.5">
              {draft.buttons.map((b) => (
                <li key={b.id}>{b.text} <span className="text-xs text-steel">{BUTTON_LABEL[b.type]}</span></li>
              ))}
            </ul>
          )}
        </Row>
        {samples.length > 0 && (
          <Row label="Samples">
            <ul className="space-y-0.5">
              {samples.map(({ key, token }) => (
                <li key={key}><span className="font-mono text-xs text-steel">{`{{${token}}}`}</span> {draft.samples[key]}</li>
              ))}
            </ul>
          </Row>
        )}
        {draft.category === 'UTILITY' && (
          <Row label="Expires after">{draft.ttl === null ? 'WhatsApp default' : ttlLabel(draft.ttl)}</Row>
        )}
        <Row label="Checks">{issues.length === 0 ? (
            <Badge variant="pill-success" size="sm">Ready to send</Badge>
          ) : (
            <span className="space-y-0.5">
              <Badge variant="pill-warning" size="sm">{issues.length === 1 ? '1 problem' : `${issues.length} problems`}</Badge>
              <span className="block text-xs text-steel">{issues[0]}</span>
            </span>
          )}</Row>
      </dl>

      <ul className="list-disc space-y-1 pl-4 text-xs text-steel">
        <li>Meta usually reviews in a few minutes, but it can take up to 24 hours.</li>
        {draft.category === 'UTILITY' && <li>Meta may move a utility template to marketing.</li>}
        <li>Samples are only used for review.</li>
      </ul>
    </StepLayout>
  );
}
