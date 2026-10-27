import { Badge } from '@/components/ui/badge';
import { qualityInfo, statusInfo, type BadgeTone } from './templateModel';

const VARIANT: Record<BadgeTone, 'pill-success' | 'pill-warning' | 'pill-danger' | 'pill-neutral'> = {
  success: 'pill-success',
  warning: 'pill-warning',
  danger: 'pill-danger',
  neutral: 'pill-neutral',
};

export function StatusBadge({ status }: { status?: string }) {
  const info = statusInfo(status);
  return <Badge variant={VARIANT[info.tone]}>{info.label}</Badge>;
}

export function QualityBadge({ score }: { score?: string }) {
  const info = qualityInfo(score);
  return info ? <Badge variant={VARIANT[info.tone]}>{info.label}</Badge> : null;
}

export function CategoryChangeBadge({ pending, to }: { pending?: boolean; to?: string }) {
  if (!pending) return null;
  return (
    <Badge variant="pill-warning" title={to ? `WhatsApp plans to move this template to ${to.toLowerCase()}.` : undefined}>
      Category change pending
    </Badge>
  );
}

export function SharedPill({ shared }: { shared?: boolean }) {
  return shared ? <Badge variant="pill-warning">Shared</Badge> : null;
}

/** "Used by" chips; renders nothing when the server sent no usage. */
export function UsedByChips({ users }: { users?: { solution: string; title: string }[] }) {
  if (!users || users.length === 0) return null;
  return (
    <span className="flex flex-wrap items-center gap-1" data-testid="used-by">
      <span className="text-[10px] font-medium uppercase tracking-wide text-steel">Used by</span>
      {users.map((u) => <Badge key={u.solution} variant="chip" size="sm">{u.title || u.solution}</Badge>)}
    </span>
  );
}
