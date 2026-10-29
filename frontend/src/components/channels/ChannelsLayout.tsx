import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { AppShellFrame } from '@/layouts/AppShellFrame';
import { ChannelsRail } from './ChannelsRail';
import { ChannelsTopbar } from './ChannelsTopbar';
import { SetupBanner } from './SetupBanner';
import { rememberGateway, useChannelGateway } from './useChannelGateway';
import { useGatewaySummary } from './useGatewaySummary';

function BannerSlot() {
  const gw = useChannelGateway();
  const { gateways } = useGatewaySummary();
  const stage = gateways.find((g) => g.name === gw)?.setup_stage;
  return <SetupBanner stage={stage} />;
}

export function ChannelsLayout() {
  const gw = useChannelGateway();
  useEffect(() => {
    if (gw) rememberGateway(gw);
  }, [gw]);
  return (
    <AppShellFrame rail={<ChannelsRail />} topbar={<ChannelsTopbar />}>
      <BannerSlot />
      <Outlet />
    </AppShellFrame>
  );
}
