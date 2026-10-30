import { Button } from '@/components/ui/button';
import type { CompleteSignupResult } from '@/services/channels/embeddedSignupApi';
import { EmbeddedSignupStep } from './EmbeddedSignupStep';

export function ChoosePathStep({
  onManual,
  onFacebookConnected,
}: {
  onManual: () => void;
  onFacebookConnected?: (result: CompleteSignupResult) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line p-4">
        <EmbeddedSignupStep onConnected={(r) => onFacebookConnected?.(r)} />
      </div>
      <div className="rounded-md border border-line p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-ink">I have a Meta app</p>
            <p className="text-sm text-steel">Paste the IDs and keys from your Meta developer dashboard.</p>
          </div>
          <Button onClick={onManual}>I have a Meta app</Button>
        </div>
      </div>
    </div>
  );
}
