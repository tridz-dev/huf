import { ItemCard } from '@/components/dashboard';
import { Badge } from '@/components/ui/badge';
import { labels, purposeLabel } from './labels';
import type { SolutionSummary } from '@/types/solutions';

interface SolutionCardProps {
  solution: SolutionSummary;
  onOpen: (name: string) => void;
}

export function SolutionCard({ solution, onOpen }: SolutionCardProps) {
  const live = solution.status === 'Live';
  const kind = solution.primary?.type ?? 'Agent';
  return (
    <ItemCard
      title={solution.title}
      description={solution.description || solution.primary?.label}
      status={{ label: live ? 'Active' : 'Paused', variant: live ? 'default' : 'secondary' }}
      onClick={() => onOpen(solution.name)}
      metadata={[
        { label: labels.purpose, value: purposeLabel(solution.purpose) },
        {
          label: labels.runsOn,
          value: (
            <span className="flex flex-wrap items-center justify-end gap-1">
              {solution.runs_on.length === 0 ? '-' : null}
              {solution.runs_on.map((r) => (
                <Badge key={r.gateway} variant="outline" size="sm">
                  {r.label}
                </Badge>
              ))}
              {solution.shared ? (
                <Badge variant="secondary" size="sm">
                  Shared
                </Badge>
              ) : null}
            </span>
          ),
        },
        { label: 'Entry points', value: solution.entry_count },
        { label: kind, value: solution.primary?.label ?? '-' },
      ]}
      footer={<span className="text-[11px] text-steel">{solution.chats_7d} chats this week</span>}
    />
  );
}
