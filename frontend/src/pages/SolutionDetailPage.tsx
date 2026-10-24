import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageFrame } from '@/layouts/PageFrame';
import { EntryPointsTab } from '@/components/solutions/EntryPointsTab';
import { SolutionConversationsTab } from '@/components/solutions/SolutionConversationsTab';
import { SolutionOverviewTab } from '@/components/solutions/SolutionOverviewTab';
import { SolutionTemplatesTab } from '@/components/solutions/SolutionTemplatesTab';
import { TestChat } from '@/components/solutions/TestChat';
import { labels } from '@/components/solutions/labels';
import { SolutionsApiError, getSolutionOverview, listEntryPoints, listSolutions } from '@/services/solutionsApi';
import type { EntryPoint, SolutionOverview } from '@/types/solutions';

const TABS = ['overview', 'entries', 'templates', 'convs', 'test'] as const;
type TabName = (typeof TABS)[number];
const asTab = (v: string | null): TabName => TABS.find((t) => t === v) ?? 'overview';

type Failure = { kind: 'not_found' | 'not_permitted' | 'error'; message: string };

function toFailure(err: unknown): Failure {
  if (err instanceof SolutionsApiError && (err.code === 'not_found' || err.code === 'not_permitted')) {
    return { kind: err.code, message: err.message };
  }
  return { kind: 'error', message: err instanceof Error ? err.message : `Could not load this ${labels.solutionLower}.` };
}

export default function SolutionDetailPage() {
  const { name = '' } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = asTab(params.get('tab'));

  const [overview, setOverview] = useState<SolutionOverview | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [checking, setChecking] = useState(false);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [entries, setEntries] = useState<EntryPoint[]>([]);

  const load = useCallback(async () => {
    try {
      setOverview(await getSolutionOverview(name));
      setFailure(null);
    } catch (err) {
      setFailure(toFailure(err));
    }
  }, [name]);

  useEffect(() => {
    setOverview(null);
    setFailure(null);
    void load();
  }, [load]);

  useEffect(() => {
    listSolutions()
      .then((list) => setTitles(Object.fromEntries(list.map((s) => [s.name, s.title]))))
      .catch(() => setTitles({}));
  }, []);

  const haveOverview = overview !== null;
  useEffect(() => {
    if (tab !== 'test' || !haveOverview) return;
    listEntryPoints(name).then(setEntries).catch(() => setEntries([]));
  }, [tab, haveOverview, name]);

  const check = async () => {
    setChecking(true);
    await load();
    setChecking(false);
  };

  const setTab = (next: string) => {
    const p = new URLSearchParams(params);
    if (next === 'overview') p.delete('tab');
    else p.set('tab', next);
    setParams(p, { replace: true });
  };

  const title = overview?.title ?? name;
  const frameTitle = (
    <span className="flex items-center gap-1.5">
      <Link to="/solutions" className="text-steel hover:text-ink">{labels.solutions}</Link>
      <span className="text-steel" aria-hidden>/</span>
      <span>{title}</span>
    </span>
  );

  const testGateways = useMemo(
    () => (overview?.runs_on ?? []).map((r) => ({ name: r.gateway, label: r.label, phone: r.phone })),
    [overview],
  );

  const chips = useMemo(() => {
    const words = entries.filter((e) => e.match_type === 'Keyword').flatMap((e) => e.match_values);
    return words.length > 0 ? words.slice(0, 4) : ['Hi', 'Hello'];
  }, [entries]);
  const adChips = useMemo(
    () => entries.filter((e) => e.match_type === 'Ad or link tag').flatMap((e) => e.match_values).slice(0, 3),
    [entries],
  );

  let body;
  if (failure) {
    body =
      failure.kind === 'not_found' ? (
        <Notice heading={`${labels.solution} not found`} text={`There is no ${labels.solutionLower} called "${name}". It may have been deleted.`}>
          <Button variant="outline" onClick={() => navigate('/solutions')}>Back to {labels.solutionsLower}</Button>
        </Notice>
      ) : failure.kind === 'not_permitted' ? (
        <Notice heading="You do not have access" text={`Ask an admin for access to manage ${labels.solutionsLower}.`}>
          <Button variant="outline" onClick={() => navigate('/solutions')}>Back to {labels.solutionsLower}</Button>
        </Notice>
      ) : (
        <Notice heading={`Could not load this ${labels.solutionLower}`} text={failure.message}>
          <Button variant="outline" onClick={() => { setFailure(null); void load(); }}>Retry</Button>
        </Notice>
      );
  } else if (!overview) {
    body = (
      <div className="space-y-3" aria-busy="true" data-testid="solution-skeleton">
        <Skeleton className="h-12" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  } else {
    body = (
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList layout="scroll" className="sm:w-auto [&>*]:shrink-0">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="entries">Entry points</TabsTrigger>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="convs">Conversations</TabsTrigger>
          <TabsTrigger value="test">Test chat</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-3">
          <SolutionOverviewTab
            overview={overview}
            solutionLabels={titles}
            checking={checking}
            onCheck={check}
            onChanged={load}
            onManageEntryPoints={() => setTab('entries')}
          />
        </TabsContent>
        <TabsContent value="entries" className="pt-3">
          <EntryPointsTab overview={overview} onChanged={load} onLoaded={setEntries} />
        </TabsContent>
        <TabsContent value="templates" className="pt-3">
          <SolutionTemplatesTab overview={overview} />
        </TabsContent>
        <TabsContent value="convs" className="pt-3">
          <SolutionConversationsTab overview={overview} solutionLabels={titles} />
        </TabsContent>
        <TabsContent value="test" className="pt-3">
          {testGateways.length === 0 ? (
            <p className="text-sm text-steel">Add a number to this {labels.solutionLower} to try it in a test chat.</p>
          ) : (
            <TestChat gateways={testGateways} chips={chips} adChips={adChips} brand={overview.title} solutionLabels={{ ...titles, [overview.name]: overview.title }} />
          )}
        </TabsContent>
      </Tabs>
    );
  }

  return (
    <PageFrame title={frameTitle}>
      <div className="space-y-3 p-4">{body}</div>
    </PageFrame>
  );
}

function Notice({ heading, text, children }: { heading: string; text: string; children?: React.ReactNode }) {
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center">
      <h2 className="text-base font-semibold text-ink">{heading}</h2>
      <p className="text-sm text-steel">{text}</p>
      {children}
    </div>
  );
}
