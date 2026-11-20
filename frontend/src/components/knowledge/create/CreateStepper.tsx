import { cn } from '@/lib/utils';

const STEPS = ['Name', 'Add content', 'Try it'];

/** "1 Name · 2 Add content · 3 Try it" progress indicator for the create flow. */
export function CreateStepper({ step }: { step: 1 | 2 | 3 }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 text-sm" data-testid="create-stepper" aria-label="Steps">
      {STEPS.map((label, i) => (
        <li key={label} className={cn('flex items-center gap-2', i + 1 === step ? 'font-medium text-ink' : 'text-steel-soft')} aria-current={i + 1 === step ? 'step' : undefined}>
          {i > 0 && <span aria-hidden>·</span>}
          <span>
            {i + 1} {label}
          </span>
        </li>
      ))}
    </ol>
  );
}
