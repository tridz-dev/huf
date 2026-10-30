import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { channelMeta } from '../channelsMeta';
import { useChannel } from '../useChannelGateway';
import { PageFrame } from '@/layouts/PageFrame';
import { SetupWizard } from '../setup/SetupWizard';

/** /channels/whatsapp/setup: connect a new number (no gateway yet). */
export default function SetupSection() {
  const navigate = useNavigate();
  const channel = channelMeta(useChannel());
  if (channel.key !== 'whatsapp') {
    return (
      <PageFrame title={`Set up ${channel.label}`}>
        <div className="space-y-3 p-5">
          <p className="text-sm text-steel">
            {channel.label} {channel.noun.toLowerCase()} are connected from the {channel.label} setup page. Once one is
            connected it appears here.
          </p>
          <Button asChild size="sm">
            <Link to={channel.setupHref}>Open {channel.label} setup</Link>
          </Button>
        </div>
      </PageFrame>
    );
  }
  return (
    <PageFrame title="Set up WhatsApp">
      <SetupWizard onGatewayCreated={(gw) => navigate(`/channels/whatsapp/n/${encodeURIComponent(gw)}/home`)} />
    </PageFrame>
  );
}
