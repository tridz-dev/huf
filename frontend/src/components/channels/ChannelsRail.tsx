import { NavLink, useNavigate } from 'react-router-dom';
import { ArrowLeft, SquareAsterisk } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CHANNEL_SECTIONS, sectionHref } from './sections';
import { useChannelGateway, rememberGateway } from './useChannelGateway';
import { useGatewaySummary } from './useGatewaySummary';

const OTHER_CHANNELS = ['Telegram', 'Slack', 'Teams'];

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
  const navigate = useNavigate();
  const { gateways } = useGatewaySummary();

  return (
    <nav aria-label="Channels" className="flex h-full w-[248px] flex-col bg-sidebar">
      <div className="space-y-1 border-b border-line p-3">
        <div className="px-1 pb-1 text-xs font-medium uppercase tracking-wide text-steel">Channel</div>
        <div className="rounded-md bg-paper-deep px-3 py-2 text-sm font-medium text-ink">WhatsApp</div>
        {OTHER_CHANNELS.map((c) => (
          <div key={c} aria-disabled="true" className="flex items-center justify-between px-3 py-1.5 text-sm text-steel-soft">
            <span>{c}</span>
            <span className="rounded bg-paper-deep px-1.5 text-xs text-steel">P2</span>
          </div>
        ))}
        {gateways.length > 0 && (
          <select
            aria-label="Number"
            className="mt-2 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm text-ink"
            value={gw ?? ''}
            onChange={(e) => {
              rememberGateway(e.target.value);
              navigate(`/channels/whatsapp/n/${encodeURIComponent(e.target.value)}/home`);
            }}
          >
            {!gw && <option value="">Select a number</option>}
            {gateways.map((g) => (
              <option key={g.name} value={g.name}>
                {g.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {CHANNEL_SECTIONS.map((s) => {
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
                to={sectionHref(s, gw)}
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
