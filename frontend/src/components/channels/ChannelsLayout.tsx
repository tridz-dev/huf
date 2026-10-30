import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { AppShellFrame } from '@/layouts/AppShellFrame';
import { ChannelsRail } from './ChannelsRail';
import { ChannelsTopbar } from './ChannelsTopbar';
import { SetupBanner } from './SetupBanner';
import { rememberGateway, useChannel, useChannelGateway } from './useChannelGateway';
import { useGatewaySummary } from './useGatewaySummary';

function BannerSlot() {
  const gw = useChannelGateway();
  const { gateways } = useGatewaySummary();
  const channel = useChannel();
  if (channel !== 'whatsapp') return null;
  const stage = gateways.find((g) => g.name === gw)?.setup_stage;
  return <SetupBanner stage={stage} />;
}

export function ChannelsLayout() {
  const gw = useChannelGateway();
  const channel = useChannel();
  useEffect(() => {
    if (gw) rememberGateway(gw, channel);
  }, [gw, channel]);
  return (
    <AppShellFrame rail={<ChannelsRail />} topbar={<ChannelsTopbar />}>
      <BannerSlot />
      <Outlet />
    </AppShellFrame>
  );
}
