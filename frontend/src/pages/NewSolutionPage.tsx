import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { labels } from '@/components/solutions/labels';
import { NameAndPurposeStep } from '@/components/solutions/wizard/NameAndPurposeStep';
import { EntryPointsStep } from '@/components/solutions/wizard/EntryPointsStep';
import { TemplatesStep } from '@/components/solutions/wizard/TemplatesStep';
import { TestStep } from '@/components/solutions/wizard/TestStep';
import { useWizardState } from '@/components/solutions/wizard/useWizardState';

const STEPS = ['Name and purpose', 'How customers reach it', 'Templates', 'Test'];

/** Four-step setup wizard. Nothing is saved until "Go live" (or leaving it in test mode). */
export default function NewSolutionPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const wiz = useWizardState({
    purpose: params.get('purpose'),
    mode: params.get('mode'),
    gateway: params.get('gateway'),
  });
  const { state, actions } = wiz;

  const finish = async () => {
    const created = await wiz.submit();
    if (!created) return;
    const title = created.title || state.name.trim();
    const path = `/solutions/${encodeURIComponent(created.name)}`;
    const message = !state.existing
      ? `${title} saved as paused. Choose what answers to take it live.`
      : state.testMode
        ? `${title} saved in test mode`
        : `${title} is live`;
    toast.success(message, { action: { label: 'Open', onClick: () => navigate(path) } });
    navigate(path);
  };

  return (
    <PageFrame title={labels.newSolution}>
      <ol className="mb-6 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i + 1 === state.step ? 'step' : undefined}
            className={cn(i + 1 === state.step ? 'font-medium text-ink' : 'text-steel')}
          >
            {i + 1}. {s}
          </li>
        ))}
      </ol>

      <div className={state.step === 4 ? 'max-w-[1100px]' : 'max-w-[760px]'}>
        {state.step === 1 && <NameAndPurposeStep wiz={wiz} />}
        {state.step === 2 && <EntryPointsStep wiz={wiz} />}
        {state.step === 3 && <TemplatesStep wiz={wiz} />}
        {state.step === 4 && <TestStep wiz={wiz} />}

        {wiz.error && (
          <p role="alert" className="mt-4 text-sm text-destructive">
            {wiz.error}
          </p>
        )}

        <div className="mt-6 flex gap-2">
          <Button type="button" variant="outline" disabled={state.step === 1 || wiz.submitting} onClick={actions.back}>
            Back
          </Button>
          {state.step < 4 ? (
            <Button type="button" disabled={!wiz.canContinue} onClick={actions.next}>
              Continue
            </Button>
          ) : (
            <Button type="button" disabled={wiz.submitting || !state.gateway} onClick={() => void finish()}>
              {wiz.submitting ? 'Saving...' : 'Go live'}
            </Button>
          )}
        </div>
      </div>
    </PageFrame>
  );
}
