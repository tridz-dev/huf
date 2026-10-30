import { TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useExecutionsAccess } from '@/hooks/permissions/useExecutionsAccess';

type Tab = 'runs' | 'flow-runs' | 'analytics';

const EXPLAINED: Record<Tab, string> = {
  runs: 'Every task or conversation an agent handled.',
  'flow-runs': 'Every time a flow ran, step by step.',
  analytics: 'Totals and trends across your runs.',
};

/** The tabs under the Executions title: what each list holds is said in words, next to the tabs. */
export function ExecutionsTabsBar({ active }: { active: Tab }) {
  const { canSeeAnalytics, canSeeFlowRuns } = useExecutionsAccess();
  return (
    <>
      <TabsList className="w-fit shrink-0" data-testid="executions-tabs">
        <TabsTrigger value="runs" title={EXPLAINED.runs} data-testid="executions-tab-runs">Agent runs</TabsTrigger>
        {canSeeFlowRuns && <TabsTrigger value="flow-runs" title={EXPLAINED['flow-runs']} data-testid="executions-tab-flow-runs">Flow runs</TabsTrigger>}
        {canSeeAnalytics && <TabsTrigger value="analytics" title={EXPLAINED.analytics} data-testid="executions-tab-analytics">Analytics</TabsTrigger>}
      </TabsList>
      <p className="hidden min-w-0 truncate text-meta text-steel sm:block" data-testid="executions-tab-hint">{EXPLAINED[active]}</p>
    </>
  );
}
