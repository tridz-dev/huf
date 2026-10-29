import { Workflow } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface FirstFlowCoachProps {
  onStart: () => void;
}

const STEPS = [
  'Choose what starts it: a web request, a schedule, or a change to a record.',
  'Add the steps it should take, one after another.',
  'Publish it when you are ready. Until then nothing runs by itself.',
];

/** The empty Flows list for someone who can create flows: a short "how it goes" and one clear first step. */
export function FirstFlowCoach({ onStart }: FirstFlowCoachProps) {
  return (
    <div
      className="mx-auto flex max-w-lg flex-col items-center gap-4 rounded-lg border border-line bg-panel p-6 text-center sm:p-8"
      role="note"
      data-testid="flow-first-run-coach"
    >
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-line bg-background text-steel">
        <Workflow className="h-5 w-5" aria-hidden />
      </span>
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">Build your first flow</h2>
        <p className="text-ui-text text-steel">A flow does something for you automatically. It takes about two minutes.</p>
      </div>
      <ol className="w-full space-y-2 text-left text-ui-text text-steel">
        {STEPS.map((text, i) => (
          <li key={i} className="flex gap-3">
            <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-signal/10 text-xs font-medium text-signal-ink">
              {i + 1}
            </span>
            <span className="min-w-0">{text}</span>
          </li>
        ))}
      </ol>
      <Button onClick={onStart} data-testid="flow-first-run-start">
        Start with a template
      </Button>
    </div>
  );
}
