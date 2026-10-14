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
