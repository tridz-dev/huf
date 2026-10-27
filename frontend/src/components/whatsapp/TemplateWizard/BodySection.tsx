import { useEffect, useRef } from 'react';
import { Bold, Braces, Code, Info, Italic, Strikethrough } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { TemplateWizardDraft } from '../template/draft';
import { toggleFormat, type FormatMark } from '../template/formatting';
import { WIZARD_LIMITS } from '../template/rules';
import { insertVariable } from '../template/variables';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';

const MARKS: { mark: FormatMark; label: string; Icon: typeof Bold }[] = [
  { mark: 'bold', label: 'Bold', Icon: Bold },
  { mark: 'italic', label: 'Italic', Icon: Italic },
  { mark: 'strike', label: 'Strikethrough', Icon: Strikethrough },
  { mark: 'mono', label: 'Code', Icon: Code },
];

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  onBody: (body: string) => void;
}

export function BodySection({ draft, field, onBody }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const pending = useRef<{ start: number; end: number } | null>(null);
  const error = field.error('body');

  // Restore the selection once React has written the edited text back.
  useEffect(() => {
    const sel = pending.current;
    const el = ref.current;
    if (!sel || !el) return;
    pending.current = null;
    el.focus();
    el.setSelectionRange(sel.start, sel.end);
  }, [draft.body]);

  const format = (mark: FormatMark) => {
    const el = ref.current;
    const edit = toggleFormat(draft.body, el?.selectionStart ?? draft.body.length, el?.selectionEnd ?? draft.body.length, mark);
    pending.current = { start: edit.selectionStart, end: edit.selectionEnd };
    onBody(edit.text);
  };

  const addVariable = () => {
    const res = insertVariable(draft.body, ref.current?.selectionStart ?? null, draft.variableType);
    pending.current = { start: res.caret, end: res.caret };
    onBody(res.text);
  };

  return (
    <Section title="Message">
      <Field
        id="tpl-body"
        label="Body"
        error={error}
        hint="Use *bold*, _italic_, ~strike~ and ```code``` formatting."
        counter={{ length: draft.body.length, max: WIZARD_LIMITS.body }}
        labelExtra={
          <Tooltip>
            <TooltipTrigger asChild>
              <button type="button" aria-label="Variable rules" className="rounded-sm text-steel focus-visible:ring-1 focus-visible:ring-ring">
                <Info className="h-4 w-4" aria-hidden />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-64">
              Variables are placeholders for real values. Number them in order without gaps, and do not start or end the message with one.
            </TooltipContent>
          </Tooltip>
        }
      >
        <div className="rounded-md border border-line focus-within:ring-1 focus-within:ring-ring">
          <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-1 border-b border-line p-1">
            {MARKS.map(({ mark, label, Icon }) => (
              <Button key={mark} type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={label} onClick={() => format(mark)}>
                <Icon className="h-4 w-4" aria-hidden />
              </Button>
            ))}
            <Button type="button" variant="ghost" size="sm" className="ml-auto h-7" onClick={addVariable}>
              <Braces className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Add variable
            </Button>
          </div>
          <Textarea
            {...controlA11y('tpl-body', error)}
            ref={ref}
            rows={7}
            value={draft.body}
            placeholder="Hi {{1}}, your order {{2}} has shipped."
            className="rounded-t-none border-0 focus-visible:ring-0"
            onChange={(e) => onBody(e.target.value)}
            onBlur={() => field.touch('body')}
          />
        </div>
      </Field>
    </Section>
  );
}
