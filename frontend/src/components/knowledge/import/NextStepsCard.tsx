import { useState } from 'react';
import { ArrowRight, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const key = (source: string) => `knowledge-next-steps-dismissed:${source}`;

export function nextStepsDismissed(source: string): boolean {
  try {
    return window.localStorage.getItem(key(source)) === '1';
  } catch {
    return false;
  }
}

interface NextStepsCardProps {
  knowledgeSource: string;
  ready: number;
  onTry: () => void;
  onConnect: () => void;
}

/** Checklist shown after the first documents are added. */
export function NextStepsCard({ knowledgeSource, ready, onTry, onConnect }: NextStepsCardProps) {
  const [hidden, setHidden] = useState(() => nextStepsDismissed(knowledgeSource));
  if (hidden) return null;
  const dismiss = () => {
    try {
      window.localStorage.setItem(key(knowledgeSource), '1');
    } catch {
      /* storage unavailable: just hide for now */
    }
    setHidden(true);
  };
  return (
    <Card data-testid="next-steps">
      <CardContent className="space-y-2 py-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Next steps</p>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Dismiss next steps" onClick={dismiss}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <ul className="space-y-1.5 text-sm">
          <li className="flex items-center gap-2 text-steel">
            <Check className="h-4 w-4 text-good" /> Documents added ({ready.toLocaleString()} ready)
          </li>
          <li>
            <button type="button" onClick={onTry} className="flex items-center gap-2 text-signal-ink hover:underline">
              <ArrowRight className="h-4 w-4" /> Try a question
            </button>
          </li>
          <li>
            <button type="button" onClick={onConnect} className="flex items-center gap-2 text-signal-ink hover:underline">
              <ArrowRight className="h-4 w-4" /> Connect to an agent
            </button>
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}
