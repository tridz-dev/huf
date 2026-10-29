import { Link } from 'react-router-dom';
import { setupStep, SETUP_TOTAL_STEPS } from './setupStage';
import { Button } from '@/components/ui/button';

export function SetupBanner({ stage }: { stage?: string | null }) {
  const n = setupStep(stage);
  if (n === null) return null;
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-line bg-paper-deep px-5 py-2 text-sm text-ink"
    >
      <span>
        Finish setup to go live ({n} of {SETUP_TOTAL_STEPS})
      </span>
      <Button asChild size="sm" variant="outline">
        <Link to="/channels/whatsapp/setup">Continue setup</Link>
      </Button>
    </div>
  );
}
