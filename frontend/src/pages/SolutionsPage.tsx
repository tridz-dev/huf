import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Boxes, Plus, ShieldCheck } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { GridView, EmptyState } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { SolutionCard } from '@/components/solutions/SolutionCard';
import { SolutionsEmptyState } from '@/components/solutions/SolutionsEmptyState';
import { PurposeFilter } from '@/components/solutions/PurposeFilter';
import { labels } from '@/components/solutions/labels';
import { getIntents, listSolutions } from '@/services/solutionsApi';
import { getGateways } from '@/services/gatewayApi';
import type { Intent, SolutionSummary } from '@/types/solutions';

export default function SolutionsPage() {
  const navigate = useNavigate();
  const [solutions, setSolutions] = useState<SolutionSummary[]>([]);
  const [intents, setIntents] = useState<Intent[]>([]);
  const [purpose, setPurpose] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [noNumber, setNoNumber] = useState(false);

  const load = useCallback(async (p: string) => {
    setLoading(true);
    setError('');
    try {
      setSolutions(await listSolutions(p || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not load ${labels.solutionsLower}.`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(purpose);
  }, [load, purpose]);

  useEffect(() => {
    getIntents().then(setIntents).catch(() => setIntents([]));
    getGateways()
      .then((gws) => setNoNumber(!gws.some((g) => g.provider === 'WhatsApp')))
      .catch(() => setNoNumber(false));
  }, []);

  const goNew = (query = '') => navigate(`/solutions/new${query}`);
  const firstTime = !loading && !error && !purpose && solutions.length === 0;

  const newButton = (
    <Button onClick={() => goNew()}>
      <Plus className="mr-1 h-4 w-4" />
      {labels.newSolution}
    </Button>
  );

  return (
    <PageFrame title={labels.solutions}>
      {noNumber && (
        <div
          role="status"
          className="mb-4 flex items-center gap-2 rounded-xl border border-line bg-panel p-3 text-sm text-steel"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            No WhatsApp number is connected yet.{' '}
            <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => navigate('/gateways')}>
              Connect a number
            </button>
          </span>
        </div>
      )}

      {firstTime ? (
        <>
          <SolutionsEmptyState
            intents={intents}
            onNew={() => goNew()}
            onPurpose={(id) => goNew(`?purpose=${encodeURIComponent(id)}`)}
            onExisting={() => goNew('?mode=existing')}
            onBlank={() => goNew('?mode=blank')}
          />
          <p className="mt-3 text-xs text-steel">
            Connected numbers reply to no one until a {labels.solutionLower} is live. A purpose only suggests templates
            and entry points; it never creates an agent for you.
          </p>
        </>
      ) : (
        <>
          <div className="mb-6 flex gap-4 rounded-xl border border-line bg-panel p-5 shadow-xs">
            <Boxes className="h-8 w-8 shrink-0 text-steel" strokeWidth={1.5} />
            <div>
              <h2 className="text-base font-semibold text-ink">{labels.solutions}</h2>
              <p className="mt-1 text-sm text-steel">
                A {labels.solutionLower} bundles the agent, flows and routing for one job. One number can run several:
                numbers carry the messages, {labels.solutionsLower} decide who answers.
              </p>
              <p className="mt-2 flex items-center gap-1.5 text-sm text-steel">
                <ShieldCheck className="h-4 w-4 text-good" />
                Only approved senders can reach your agents.
              </p>
            </div>
          </div>

          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-ink">{labels.activeSolutions}</h2>
              <p className="text-sm text-steel">
                Group the agents, flows and templates for one job, across one or more numbers.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <PurposeFilter value={purpose} onChange={setPurpose} intents={intents} />
              {newButton}
            </div>
          </div>

          {error ? (
            <div role="alert" className="rounded-xl border border-line bg-panel p-5 text-sm">
              <p className="text-destructive">{error}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => void load(purpose)}>
                Try again
              </Button>
            </div>
          ) : (
            <GridView
              items={solutions}
              loading={loading}
              columns={{ sm: 1, md: 2, lg: 3 }}
              keyExtractor={(s) => s.name}
              emptyState={
                <EmptyState
                  variant="no-results"
                  icon={Boxes}
                  title={`No ${labels.solutionsLower} for this purpose`}
                  description="Try another purpose."
                />
              }
              renderItem={(s) => <SolutionCard solution={s} onOpen={(n) => navigate(`/solutions/${encodeURIComponent(n)}`)} />}
            />
          )}
        </>
      )}
    </PageFrame>
  );
}
