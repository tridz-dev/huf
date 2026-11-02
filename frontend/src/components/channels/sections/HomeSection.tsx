import { useState } from 'react';
import { PageFrame } from '@/layouts/PageFrame';
import { HomeDashboard } from '../home/HomeDashboard';
import { SETUP_STEP_TITLES, SETUP_TOTAL_STEPS, stageRank } from '../setupStage';
import { SetupWizard } from '../setup/SetupWizard';
import { useSetupStatus } from '../setup/useSetupStatus';
import { ChannelHome } from '../home/ChannelHome';
import { useChannel, useChannelGateway } from '../useChannelGateway';

function SetupProgress({ step }: { step: number }) {
  const next = SETUP_STEP_TITLES[Math.min(step, SETUP_TOTAL_STEPS) - 1];
  return (
    <div role="status" className="mx-5 mt-5 rounded-md border border-line bg-paper-deep p-4">
      <p className="text-sm font-medium text-ink">
        Setup progress: {step} of {SETUP_TOTAL_STEPS}
      </p>
      <p className="text-sm text-steel">Next: {next}</p>
    </div>
  );
}

export default function HomeSection() {
  const gateway = useChannelGateway();
  const channel = useChannel();
  const status = useSetupStatus(channel === 'whatsapp' ? gateway : undefined, false);
  const [finished, setFinished] = useState(false);
  const [step, setStep] = useState(1);

  if (!gateway) return null;
  if (channel !== 'whatsapp') {
    return (
      <PageFrame title="Home">
        <ChannelHome gateway={gateway} />
      </PageFrame>
    );
  }
  if (!status.loaded) {
    return (
      <PageFrame title="Home">
        <div className="p-5 text-sm text-steel" role="status">
          Loading...
        </div>
      </PageFrame>
    );
  }
  // Only the pre-live stages get the wizard; live, off, blocked and degraded numbers get the
  // dashboard (its health banner handles problems). The stage is read once, so the wizard stays
  // up through the access-policy step even after binding an agent makes the stage read "live".
  const rank = stageRank(status.stage);
  const wizard = !finished && rank >= 0 && rank < 4;
  if (!wizard) {
    return (
      <PageFrame title="Home">
        <HomeDashboard gateway={gateway} />
      </PageFrame>
    );
  }
  return (
    <PageFrame title="Home">
      <SetupProgress step={step} />
      <SetupWizard gateway={gateway} onStepChange={setStep} onDone={() => setFinished(true)} />
    </PageFrame>
  );
}
