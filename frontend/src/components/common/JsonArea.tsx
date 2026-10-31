import { useId, useMemo, useState, type ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { copyText } from '@/lib/clipboard';
import { cn } from '@/lib/utils';
import { describeJsonProblem, formatJsonText } from '@/lib/flow-run/jsonErrors';

/**
 * The one place legitimate JSON is shown or edited (UX_NON_TECHNICAL_RULES, intentional-JSON exception): a clear
 * title, plain help above it, monospace pretty-printed text, Copy, Format, a readable error that points at the
 * line, a fold for long content and, when a friendly form exists, a "Show as form" / "Edit as JSON" switch that
 * remembers the choice per `surfaceKey`.
 *
 * Test ids: `flow-json-<key>` (root), `-input`, `-format`, `-copy`, `-error`, `-toggle`, `-more`.
 */

const COLLAPSE_LINES = 12;
const MODE_PREFIX = 'huf.jsonarea.mode.';

type Mode = 'form' | 'json';

function readMode(key: string): Mode | null {
  try {
    const v = window.localStorage.getItem(MODE_PREFIX + key);
    return v === 'form' || v === 'json' ? v : null;
  } catch {
    return null;
  }
}

function writeMode(key: string, mode: Mode) {
  try {
    window.localStorage.setItem(MODE_PREFIX + key, mode);
  } catch {
    // Private window or blocked storage: the choice just is not remembered.
  }
}

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

/** Light syntax colour: names, text, numbers and true / false / null. Plain spans, no library. */
function highlightJson(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const cls = m[1] ? (m[2] ? 'text-signal-ink' : 'text-good') : m[3] ? 'text-warning' : 'text-steel';
    out.push(<span key={n++} className={cls}>{m[1] ? m[1] : m[0]}</span>);
    if (m[2]) out.push(m[2]);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export interface JsonAreaProps {
  /** Short, stable name of the place this sits in; builds the test ids and the remembered form/JSON choice. */
  surfaceKey: string;
  /** Plain title, e.g. "Request body (JSON)" or "Raw data". */
  title: string;
  /** What it is, when to edit it and what happens when it is wrong. Shown above the text. */
  help?: ReactNode;
  value: string;
  onChange?: (next: string) => void;
  /** Show only (Copy and fold stay). */
  readOnly?: boolean;
  /** A box left empty is fine (no error). */
  allowEmpty?: boolean;
  /** The friendly view of the same data. When given, the area opens as this form until the user chooses JSON. */
  formView?: ReactNode;
  /** Shown in an empty box: a small example so nobody starts from nothing. */
  placeholder?: string;
  className?: string;
  /** Extra id wrapped around the text only (keeps older step-output ids pointing at the data). */
  textTestId?: string;
  /** Read-only areas: what Copy puts on the clipboard when it must differ from the text shown. */
  copyValue?: string;
}

export function JsonArea({ surfaceKey, title, help, value, onChange, readOnly = false, allowEmpty = true, formView, placeholder, className, textTestId, copyValue }: JsonAreaProps) {
  const base = `flow-json-${surfaceKey}`;
  const titleId = useId();
  const [mode, setMode] = useState<Mode>(() => (formView ? readMode(surfaceKey) ?? 'form' : 'json'));
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // A read-only value is shown pretty-printed whatever shape it came in.
  const shown = useMemo(() => (readOnly ? formatJsonText(value) ?? value : value), [readOnly, value]);
  const lineCount = shown.split('\n').length;
  const long = lineCount > COLLAPSE_LINES;
  const folded = long && !expanded;
  const problem = !readOnly && (value.trim() !== '' || !allowEmpty) ? (value.trim() === '' ? { line: 1, message: 'Enter some JSON here, or remove this setting.' } : describeJsonProblem(value)) : null;

  const switchMode = (next: Mode) => {
    setMode(next);
    writeMode(surfaceKey, next);
  };

  const copy = async () => {
    if (await copyText(copyValue ?? shown)) {
      setCopied(true);
      toast.success('Copied');
      setTimeout(() => setCopied(false), 1500);
    } else {
      toast.error("Couldn't copy. Select the text and copy it yourself.");
    }
  };

  const format = () => {
    const pretty = formatJsonText(value);
    if (pretty !== null) onChange?.(pretty);
  };

  return (
    <div className={cn('min-w-0 max-w-full rounded-md border border-line bg-panel', className)} data-testid={base} data-mode={mode}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-2">
        <h4 id={titleId} className="mr-auto text-sm font-medium text-ink">{title}</h4>
        {mode === 'json' && !readOnly && (
          <Button type="button" variant="ghost" size="sm" onClick={format} disabled={!!problem || value.trim() === ''} data-testid={`${base}-format`}>
            Format
          </Button>
        )}
        {mode === 'json' && (
          <Button type="button" variant="ghost" size="sm" onClick={copy} disabled={shown.trim() === ''} data-testid={`${base}-copy`}>
            {copied ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
        )}
        {formView && (
          <Button type="button" variant="ghost" size="sm" onClick={() => switchMode(mode === 'json' ? 'form' : 'json')} data-testid={`${base}-toggle`}>
            {mode === 'json' ? 'Show as form' : 'Edit as JSON'}
          </Button>
        )}
      </div>
      {help && <p className="px-3 pt-2 text-meta leading-snug text-muted-foreground break-words" data-testid={`${base}-help`}>{help}</p>}
      <div className="p-3">
        {mode === 'form' && formView ? (
          formView
        ) : readOnly ? (
          <div data-testid={textTestId}>
            <pre
              aria-labelledby={titleId}
              className={cn('whitespace-pre-wrap [overflow-wrap:anywhere] rounded bg-muted p-2 font-mono text-xs leading-relaxed', folded && 'max-h-[17rem] overflow-hidden')}
              data-testid={`${base}-text`}
            >
              {highlightJson(shown)}
            </pre>
          </div>
        ) : (
          <Textarea
            aria-labelledby={titleId}
            aria-invalid={!!problem}
            aria-describedby={problem ? `${titleId}-error` : undefined}
            spellCheck={false}
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange?.(e.target.value)}
            rows={Math.min(Math.max(lineCount, 4), folded ? COLLAPSE_LINES : 40)}
            className={cn('min-h-0 resize-y bg-muted p-2 font-mono text-xs leading-relaxed', problem && 'border-destructive')}
            data-testid={`${base}-input`}
          />
        )}
        {mode === 'json' && long && (
          <button type="button" className="mt-1 text-xs font-medium text-primary underline" onClick={() => setExpanded((v) => !v)} data-testid={`${base}-more`}>
            {expanded ? 'Show less' : `Show all ${lineCount} lines`}
          </button>
        )}
        {mode === 'json' && problem && (
          <p id={`${titleId}-error`} role="alert" className="mt-2 text-xs text-destructive" data-testid={`${base}-error`}>
            {problem.message}
          </p>
        )}
      </div>
    </div>
  );
}
