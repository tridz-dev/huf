import { useState } from 'react';
import { CheckCircle2, ChevronDown, Circle, CircleDashed } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { CopyField } from '@/components/ui/copy-field';
import { getGatewayWebhookUrl } from '@/utils/gatewayWebhook';
import { TEAMS_PROVIDER, TEAMS_STEPS, deriveStepStates, type ReadinessCheckLike, type StepState } from './teamsOnboarding';
import { TeamsManifestDownload } from './TeamsManifestDownload';
import { TeamsVerifyConnection } from './TeamsVerifyConnection';

interface TeamsSetupGuideProps {
  gatewayName: string;
  checks?: ReadinessCheckLike[] | null;
}

const STATE_LABEL: Record<StepState, string> = { done: 'Done', todo: 'Not done', manual: 'Check manually' };

function StateIcon({ state }: { state: StepState }) {
  const cls = 'mt-0.5 h-4 w-4 shrink-0';
  if (state === 'done') return <CheckCircle2 className={`${cls} text-success`} aria-label={STATE_LABEL.done} />;
  if (state === 'todo') return <Circle className={`${cls} text-warning`} aria-label={STATE_LABEL.todo} />;
  return <CircleDashed className={`${cls} text-muted-foreground`} aria-label={STATE_LABEL.manual} />;
}

export function TeamsSetupGuide({ gatewayName, checks }: TeamsSetupGuideProps) {
  const [open, setOpen] = useState(true);
  const states = deriveStepStates(checks);
  const endpoint = getGatewayWebhookUrl(gatewayName, TEAMS_PROVIDER);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border p-4">
      <CollapsibleTrigger className="flex w-full items-center justify-between text-left">
        <span className="text-sm font-medium">Microsoft Teams setup guide</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-4">
        <ol className="space-y-3">
          {TEAMS_STEPS.map((step, i) => (
            <li key={step.id} className="flex gap-2">
              <StateIcon state={states[step.id]} />
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-sm font-medium">
                  {i + 1}. {step.title}
                </p>
                <p className="text-xs text-muted-foreground">{step.body}</p>
                {step.id === 'endpoint' && <CopyField label="Messaging endpoint" value={endpoint} />}
                {step.id === 'package' && <TeamsManifestDownload gatewayName={gatewayName} />}
              </div>
            </li>
          ))}
        </ol>

        <div className="space-y-2 border-t pt-3">
          <p className="text-sm font-medium">Verify connection</p>
          <p className="text-xs text-muted-foreground">
            Checks credentials, token request, endpoint and stored conversation without sending a message.
          </p>
          <TeamsVerifyConnection gatewayName={gatewayName} />
        </div>

        <div className="space-y-1 border-t pt-3">
          <p className="text-sm font-medium">Permissions and consent</p>
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
            <li>The bot reads messages sent to it in personal and group chats, and @mentions in channels.</li>
            <li>It does not see other channel or chat messages unless your tenant grants resource-specific consent (verify in your tenant).</li>
            <li>No Microsoft Graph admin consent is required for plain bot messaging (verify in your tenant).</li>
            <li>Uploading a custom app needs the custom app upload policy, or a Teams admin to upload it (verify in your tenant).</li>
            <li>Teams test send needs a conversation: message the bot first.</li>
          </ul>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
