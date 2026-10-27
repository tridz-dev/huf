import { useRef, useState } from 'react';
import { Braces, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { errorText, uploadPublicFile } from '@/services/whatsappApi';
import type { TemplateWizardDraft, WizardHeader, WizardHeaderType } from '../template/draft';
import { WIZARD_LIMITS } from '../template/rules';
import { findVariableTokens, insertVariable } from '../template/variables';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';

const TYPES: { value: WizardHeaderType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'text', label: 'Text' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
  { value: 'document', label: 'Document' },
  { value: 'location', label: 'Location' },
];

const ACCEPT: Partial<Record<WizardHeaderType, string>> = {
  image: 'image/jpeg,image/png',
  video: 'video/mp4',
  document: 'application/pdf',
};

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  onHeader: (patch: Partial<WizardHeader>) => void;
}

export function HeaderSection({ draft, field, onHeader }: Props) {
  const { header } = draft;
  const textRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const textError = field.error('header.text');
  const mediaError = field.error('header.mediaSample');
  const hasVariable = findVariableTokens(header.text).length > 0;
  const isMedia = header.type === 'image' || header.type === 'video' || header.type === 'document';

  const addVariable = () => {
    const res = insertVariable(header.text, textRef.current?.selectionStart ?? null, draft.variableType);
    onHeader({ text: res.text });
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    const res = await uploadPublicFile(file);
    setUploading(false);
    if ('fileUrl' in res) {
      onHeader({ mediaSample: res.fileUrl });
      field.touch('header.mediaSample');
    } else toast.error(errorText(res));
  };

  return (
    <Section title="Header" description="Optional. Shown above the message.">
      <ToggleGroup
        type="single"
        variant="outline"
        aria-label="Header type"
        value={header.type}
        className="flex-wrap justify-start"
        onValueChange={(v) => v && onHeader({ type: v as WizardHeaderType })}
      >
        {TYPES.map((t) => <ToggleGroupItem key={t.value} value={t.value}>{t.label}</ToggleGroupItem>)}
      </ToggleGroup>

      {header.type === 'text' && (
        <Field
          id="tpl-header-text"
          label="Header text"
          error={textError}
          hint="One variable at most."
          counter={{ length: header.text.length, max: WIZARD_LIMITS.headerText }}
          labelExtra={
            <Button type="button" variant="outline" size="sm" disabled={hasVariable} onClick={addVariable}>
              <Braces className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Add variable
            </Button>
          }
        >
          <Input
            {...controlA11y('tpl-header-text', textError)}
            ref={textRef}
            value={header.text}
            onChange={(e) => onHeader({ text: e.target.value })}
            onBlur={() => field.touch('header.text')}
          />
        </Field>
      )}

      {isMedia && (
        <Field
          id="tpl-header-media"
          label="Sample file"
          error={mediaError}
          hint="Paste a public https link to an example file, or upload one. It is only used for review."
        >
          <div className="flex gap-2">
            <Input
              {...controlA11y('tpl-header-media', mediaError)}
              value={header.mediaSample}
              placeholder="https://example.com/sample.png"
              onChange={(e) => onHeader({ mediaSample: e.target.value })}
              onBlur={() => field.touch('header.mediaSample')}
            />
            <Button type="button" variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden /> : <Upload className="mr-1.5 h-4 w-4" aria-hidden />}
              Upload
            </Button>
            <input
              ref={fileRef}
              type="file"
              hidden
              aria-label="Upload sample file"
              accept={ACCEPT[header.type]}
              onChange={(e) => {
                void upload(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
          </div>
        </Field>
      )}
    </Section>
  );
}
