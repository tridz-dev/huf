import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { copyText } from '@/lib/clipboard';

/**
 * A short command or snippet for developers: monospace, wrapped at spaces and, for a token longer than the box (a web
 * address), anywhere, so no line is ever cut at the right edge (final2-05; the Copy button copies the exact text),
 * with a labelled Copy button. Test ids: `<testId>` (the text), `<testId>-copy`.
 */
export function CodeBlock({ title, text, testId }: { title: string; text: string; testId: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (await copyText(text)) {
      setCopied(true);
      toast.success('Copied');
      setTimeout(() => setCopied(false), 1500);
    } else {
      toast.error("Couldn't copy. Select the text and copy it yourself.");
    }
  };
  return (
    <div className="rounded-md border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <h4 className="mr-auto text-sm font-medium text-ink">{title}</h4>
        <Button type="button" variant="ghost" size="sm" onClick={copy} data-testid={`${testId}-copy`}>
          {copied ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap p-3 [overflow-wrap:anywhere] font-mono text-xs leading-relaxed" tabIndex={0} data-testid={testId}>{text}</pre>
    </div>
  );
}
