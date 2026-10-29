import { useLocation } from 'react-router-dom';
import { channelMeta } from './channelsMeta';
import { sectionFromPath } from './sections';

export function ChannelsTopbar() {
  const { pathname } = useLocation();
  const channel = channelMeta(pathname.split('/')[2]);
  const rest = pathname.replace(/^\/channels\/[^/]+\/?/, '');
  const section = sectionFromPath(pathname)?.label ?? (rest.startsWith('setup') ? 'Setup' : undefined);
  const crumbs = ['Channels', channel.label, ...(section ? [section] : [])];
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-steel">
      {crumbs.map((c, i) => (
        <span key={c} className="flex items-center gap-1.5">
          {i > 0 && <span aria-hidden>/</span>}
          <span className={i === crumbs.length - 1 ? 'text-ink' : undefined}>{c}</span>
        </span>
      ))}
    </nav>
  );
}
