import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, SquareAsterisk } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useUser } from '@/contexts/UserContext';
import { cn } from '@/lib/utils';
import { SETUP_STEP_TITLES, stageRank, wizardStep } from '../setupStage';
import { AccessPolicyStep } from './AccessPolicyStep';
import { ChoosePathStep } from './ChoosePathStep';
import { CredentialsStep } from './CredentialsStep';
import { latestInboundText } from './setupApi';
import { TestStep } from './TestStep';
import { useSetupStatus } from './useSetupStatus';
import { WebhookStep } from './WebhookStep';
import { WhoAnswersStep } from './WhoAnswersStep';

export interface SetupWizardProps {
  /** Existing gateway to resume; omit to set up a new number. */
  gateway?: string;
  /** New number: called once its credentials are saved. */
  onGatewayCreated?: (gateway: string) => void;
  /** Reports the stepper position (1-6) as it changes. */
  onStepChange?: (step: number) => void;
  onDone?: () => void;
}

export function SetupWizard({ gateway, onGatewayCreated, onStepChange, onDone }: SetupWizardProps) {
  const navigate = useNavigate();
  const { user } = useUser();
  const status = useSetupStatus(gateway, true);
  const [step, setStep] = useState(1);
  const [verifyToken, setVerifyToken] = useState<string | null>(null);
  const [inbound, setInbound] = useState<string | null>(null);
  const resumed = useRef(false);

  const rank = stageRank(status.stage);
  const implied = wizardStep(status.stage);

  // Resume at the step the server says, then only ever move forward as the stage advances.
  useEffect(() => {
    if (!status.loaded || !gateway) return;
    setStep((s) => (resumed.current ? Math.max(s, implied) : implied));
    resumed.current = true;
  }, [status.loaded, gateway, implied]);

  useEffect(() => onStepChange?.(step), [step, onStepChange]);

  const testing = step === 4 && !!gateway;
  useEffect(() => {
    if (!testing || !gateway || rank < 2) return;
    let live = true;
    void latestInboundText(gateway).then((t) => live && t && setInbound(t));
    return () => {
      live = false;
    };
  }, [testing, gateway, rank, status.gateway]);

  const finish = () => {
    if (gateway) navigate(`/channels/whatsapp/n/${encodeURIComponent(gateway)}/home`);
    onDone?.();
  };

  if (gateway && !status.loaded) {
    return (
      <div className="p-5 text-sm text-steel" role="status">
        Loading setup...
      </div>
    );
  }

  const gw = status.gateway;
  let body: React.ReactNode = null;
  if (step === 1) body = <ChoosePathStep onManual={() => setStep(2)} />;
  else if (step === 2)
    body = (
      <CredentialsStep
        gateway={gateway}
        executionUser={user?.name}
        onSaved={(name, token) => {
          setVerifyToken(token);
          setStep(3);
          if (name !== gateway) onGatewayCreated?.(name);
          else void status.refresh();
        }}
      />
    );
  else if (gateway && step === 3)
    body = <WebhookStep gateway={gateway} webhookUrl={gw?.webhook_url} verifyToken={verifyToken} verified={rank >= 2} />;
  else if (gateway && step === 4)
    body = <TestStep phone={gw?.token_check?.phone?.display} done={rank >= 3} inboundText={inbound} onSkip={() => setStep(5)} />;
  else if (gateway && step === 5)
    body = <WhoAnswersStep gateway={gateway} onBound={() => setStep(6)} />;
  else if (gateway && step === 6)
    body = <AccessPolicyStep gateway={gateway} current={gw?.policy?.direct_policy} onDone={finish} />;

  return (
    <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="grid gap-5 md:grid-cols-[200px_minmax(0,1fr)]">
        <ol className="space-y-1" aria-label="Setup steps">
          {SETUP_STEP_TITLES.map((title, i) => {
            const n = i + 1;
            const done = n < step;
            return (
              <li
                key={title}
                aria-current={n === step ? 'step' : undefined}
                data-state={done ? 'done' : n === step ? 'current' : 'todo'}
                className={cn(
                  'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                  n === step ? 'bg-paper-deep font-medium text-ink' : 'text-steel',
                )}
              >
                <span
                  className={cn(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs',
                    done ? 'border-good bg-good text-primary-foreground' : 'border-line',
                  )}
                >
                  {done ? <Check className="h-3 w-3" aria-hidden /> : n}
                </span>
                {title}
              </li>
            );
          })}
        </ol>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Step {step} of {SETUP_STEP_TITLES.length}: {SETUP_STEP_TITLES[step - 1]}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {status.error && (
              <p role="alert" className="mb-3 text-sm text-destructive">
                {status.error}
              </p>
            )}
            {body}
          </CardContent>
        </Card>
      </div>
      <Card className="h-fit">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <SquareAsterisk className="h-4 w-4" aria-hidden />
            Ask Hub instead
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-steel">
          <p>Prefer to chat? Hub can walk you through connecting WhatsApp. Say "connect my WhatsApp". Secrets stay in a private form.</p>
          <Link className="text-primary underline-offset-2 hover:underline" to="/">
            Open Hub
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
