import { NavLink, useNavigate } from 'react-router-dom';
import { ArrowLeft, SquareAsterisk } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { CHANNELS, channelEnabled, channelMeta } from './channelsMeta';
import { sectionsFor, sectionHref } from './sections';
import { useChannel, useChannelGateway, rememberGateway } from './useChannelGateway';
import { useAllGateways } from './useGatewaySummary';


const itemClass = (active: boolean) =>
  cn(
    'relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink-soft hover:bg-paper-deep',
    active && 'bg-paper-deep text-ink font-medium'
  );

function ActiveBar() {
  return <span aria-hidden data-testid="active-bar" className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-signal" />;
}

export function ChannelsRail() {
  const gw = useChannelGateway();
  const channel = useChannel();
  const meta = channelMeta(channel);
  const navigate = useNavigate();
  const { byChannel } = useAllGateways();
  const gateways = byChannel[channel];

  return (
    <nav aria-label="Channels" className="flex h-full w-[248px] flex-col bg-sidebar">
      <div className="space-y-1 border-b border-line p-3">
        <div className="px-1 pb-1 text-xs font-medium uppercase tracking-wide text-steel">Channel</div>
        {CHANNELS.map((c) => {
          const Icon = c.icon;
          if (c.key === channel) {
            return (
              <div key={c.key} aria-current="true" className="flex items-center gap-2 rounded-md bg-paper-deep px-3 py-2 text-sm font-medium text-ink">
                <Icon className="h-4 w-4" />
                {c.label}
              </div>
            );
          }
          if (!channelEnabled(c.key, byChannel[c.key].length)) {
            return (
              <div key={c.key} aria-disabled="true" title={`No ${c.label} ${c.noun.toLowerCase()} connected`} className="flex items-center gap-2 px-3 py-1.5 text-sm text-steel-soft">
                <Icon className="h-4 w-4" />
                <span>{c.label}</span>
              </div>
            );
          }
          return (
            <NavLink key={c.key} to={`/channels/${c.key}`} className={() => itemClass(false)}>
              <Icon className="h-4 w-4" />
              {c.label}
            </NavLink>
          );
        })}
        {gateways.length > 0 && (
          <Select
            value={gw ?? ''}
            onValueChange={(v) => {
              rememberGateway(v, channel);
              navigate(`/channels/${channel}/n/${encodeURIComponent(v)}/home`);
            }}
          >
            <SelectTrigger size="sm" className="mt-2" aria-label={meta.nounSingular.replace(/^./, (x) => x.toUpperCase())}>
              <SelectValue placeholder={`Select a ${meta.nounSingular}`} />
            </SelectTrigger>
            <SelectContent>
              {gateways.map((g) => (
                <SelectItem key={g.name} value={g.name}>
                  {g.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {sectionsFor(channel).map((s) => {
          const gatewayless = s.key === 'numbers';
          const disabled = !gw && !gatewayless;
          const Icon = s.icon;
          if (disabled) {
            return (
              <li key={s.key}>
                <span aria-disabled="true" className="flex items-center gap-2.5 px-3 py-2 text-sm text-steel-soft">
                  <Icon className="h-4 w-4" />
                  {s.label}
                </span>
              </li>
            );
          }
          return (
            <li key={s.key}>
              <NavLink
                to={sectionHref(s, gw, channel)}
                end={false}
                className={({ isActive }) => itemClass(isActive)}
              >
                {({ isActive }) => (
                  <>
                    {isActive && <ActiveBar />}
                    <Icon className="h-4 w-4" />
                    {s.label}
                  </>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>

      <div className="space-y-0.5 border-t border-line p-2">
        <NavLink to="/" className={() => itemClass(false)}>
          <SquareAsterisk className="h-4 w-4" />
          Ask Hub
        </NavLink>
        <NavLink to="/" className={() => itemClass(false)}>
          <ArrowLeft className="h-4 w-4" />
          Back to Huf
        </NavLink>
      </div>
    </nav>
  );
}
