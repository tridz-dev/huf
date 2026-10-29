import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '../ui/button';
import { FIRST_RUN_STEPS } from '@/lib/flow/flowHelp';

const KEY = 'huf.flow.firstRunGuide.dismissed';

function dismissedBefore(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

/** Three-step hint shown on an empty canvas. Can be closed for good; the header Help button repeats it. */
export function FirstRunGuide() {
  const [hidden, setHidden] = useState(dismissedBefore);
  if (hidden) return null;
  return (
    <div className="pointer-events-auto w-[320px] max-w-full rounded-lg border border-border bg-card p-3 text-xs shadow-sm" data-testid="flow-first-run-guide">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold">Build your first flow</p>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Hide this guide"
          data-testid="flow-first-run-guide-close"
          onClick={() => {
            try {
              window.localStorage.setItem(KEY, '1');
            } catch {
              /* ignore: the guide just comes back next time */
            }
            setHidden(true);
          }}
        >
          <X className="w-3.5 h-3.5" />
        </Button>
      </div>
      <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-muted-foreground">
        {FIRST_RUN_STEPS.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <p className="mt-1.5 text-muted-foreground">Need more? Use the ? button at the top for tips and shortcuts.</p>
    </div>
  );
}
