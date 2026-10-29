import { useNavigate } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { SetupWizard } from '../setup/SetupWizard';

/** /channels/whatsapp/setup: connect a new number (no gateway yet). */
export default function SetupSection() {
  const navigate = useNavigate();
  return (
    <PageFrame title="Set up WhatsApp">
      <SetupWizard onGatewayCreated={(gw) => navigate(`/channels/whatsapp/n/${encodeURIComponent(gw)}/home`)} />
    </PageFrame>
  );
}
