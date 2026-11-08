import { ApprovalsSection } from './ApprovalsSection';
import { ConnectionsSection } from './ConnectionsSection';
import { SessionsSection } from './SessionsSection';

export function ExternalAgentsPanel() {
  return (
    <div className="flex flex-col gap-8">
      <p className="text-sm text-steel">
        Let your own AI app use Huf's tools and data with your permissions. Anything that changes records or sends messages can ask for your approval first.
      </p>
      <ApprovalsSection />
      <ConnectionsSection />
      <SessionsSection />
    </div>
  );
}
