import { Button } from '@/components/ui/button';
import { setPhoneFlowView, usePhoneFlowView } from './usePhoneFlowView';

/** The one-line note on a phone: editing is for a bigger screen, everything else works here. */
export function PhoneBanner() {
  const { view } = usePhoneFlowView();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-paper-deep px-4 py-2 text-xs text-steel" data-testid="flow-phone-banner" role="note">
      <p className="min-w-0 flex-1">Editing steps works best on a larger screen. You can still run, approve, and publish here.</p>
      <Button type="button" variant="outline" size="sm" className="min-h-11" data-testid="flow-phone-view-steps" onClick={() => setPhoneFlowView('steps')} disabled={view === 'steps'}>
        View steps
      </Button>
    </div>
  );
}
