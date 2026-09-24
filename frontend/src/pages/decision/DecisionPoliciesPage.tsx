import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { GitBranch, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { FilterBar, EmptyState } from '@/components/dashboard';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { usePermissions } from '@/contexts/PermissionsContext';
import { RuntimeDisabledBanner } from '@/components/decision/RuntimeDisabledBanner';
import { listDecisionModels, type DecisionModel } from '@/services/decisionApi';

export { DecisionPoliciesPage };
export default DecisionPoliciesPage;

const PURPOSE_OPTIONS = [
  { label: 'All purposes', value: 'all' },
  { label: 'Generic', value: 'Generic' },
  { label: 'Flow Routing', value: 'Flow Routing' },
  { label: 'Model Routing', value: 'Model Routing' },
  { label: 'Agent Routing', value: 'Agent Routing' },
  { label: 'Tool Selection', value: 'Tool Selection' },
  { label: 'Skill Selection', value: 'Skill Selection' },
  { label: 'Procedure Selection', value: 'Procedure Selection' },
  { label: 'RAG Filtering', value: 'RAG Filtering' },
  { label: 'Context Relevance', value: 'Context Relevance' },
  { label: 'Input Guardrail', value: 'Input Guardrail' },
  { label: 'Output Guardrail', value: 'Output Guardrail' },
  { label: 'Output Verification', value: 'Output Verification' },
];

const STATUS_OPTIONS = [
  { label: 'All status', value: 'all' },
  { label: 'Draft', value: 'Draft' },
  { label: 'Published', value: 'Published' },
  { label: 'Retired', value: 'Retired' },
];

interface DecisionPolicyRow {
  name: string;
  policy_name?: string;
  purpose?: string;
  default_model?: string;
  current_version?: string;
  enabled?: 0 | 1;
  modified?: string;
}

interface VersionSummary {
  status: string;
  version_number: number;
}

interface PolicyReference {
  flow_name: string;
  node_id: string;
}

function statusVariant(status: string): 'default' | 'success' | 'secondary' | 'outline' {
  if (status === 'Published') return 'success';
  if (status === 'Retired') return 'secondary';
  return 'outline';
}

function DecisionPoliciesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasCapability } = usePermissions();
  const canAuthor = hasCapability('decision.author');
  const isAdmin = hasCapability('decision.admin');

  const [loading, setLoading] = useState(true);
  const [policies, setPolicies] = useState<DecisionPolicyRow[]>([]);
  const [versionByPolicy, setVersionByPolicy] = useState<Record<string, VersionSummary>>({});
  const [modelsByName, setModelsByName] = useState<Record<string, DecisionModel>>({});
  const [flowRefsByPolicy, setFlowRefsByPolicy] = useState<Record<string, PolicyReference[]>>({});
  const [bindingCountByPolicy, setBindingCountByPolicy] = useState<Record<string, number> | null>(null);

  const [search, setSearch] = useState(searchParams.get('q') || '');
  const [purpose, setPurpose] = useState(searchParams.get('purpose') || 'all');
  const [status, setStatus] = useState(searchParams.get('status') || 'all');

  useEffect(() => {
    void loadAll();
  }, []);

  const updateSearchParams = (next: { q?: string; purpose?: string; status?: string }) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      for (const [key, value] of Object.entries(next)) {
        if (value && value !== 'all') sp.set(key, value);
        else sp.delete(key);
      }
      return sp;
    });
  };

  async function loadAll() {
    setLoading(true);
    try {
      const rows = (await db.getDocList(doctype['Decision Policy'], {
        fields: ['name', 'policy_name', 'purpose', 'default_model', 'current_version', 'enabled', 'modified'],
        orderBy: { field: 'modified', order: 'desc' },
        limit: 500,
      })) as DecisionPolicyRow[];
      setPolicies(rows);

      const names = rows.map((r) => r.name);

      // Latest version status per policy (for the Status column/filter).
      if (names.length) {
        try {
          const versions = (await db.getDocList(doctype['Decision Policy Version'], {
            fields: ['policy', 'status', 'version_number'],
            filters: [['policy', 'in', names]],
            orderBy: { field: 'version_number', order: 'desc' },
            limit: 2000,
          })) as { policy: string; status: string; version_number: number }[];
          const latest: Record<string, VersionSummary> = {};
          for (const v of versions) {
            if (!latest[v.policy]) latest[v.policy] = { status: v.status, version_number: v.version_number };
          }
          setVersionByPolicy(latest);
        } catch (error) {
          handleFrappeError(error, 'Error loading policy versions');
        }
      }

      // Bindings ("Used by" agents) -- Agent Decision Binding is a child table; query
      // it directly. If the caller lacks permission, fall back to Flow references only.
      if (names.length) {
        try {
          const response = await call.get('frappe.client.get_list', {
            doctype: doctype['Agent Decision Binding'],
            filters: [['policy', 'in', names]],
            fields: ['policy', 'parent'],
            limit_page_length: 0,
          });
          const bindingRows = (response.message || []) as { policy: string; parent: string }[];
          const counts: Record<string, Set<string>> = {};
          for (const row of bindingRows) {
            if (!counts[row.policy]) counts[row.policy] = new Set();
            counts[row.policy].add(row.parent);
          }
          const flat: Record<string, number> = {};
          for (const [policy, agents] of Object.entries(counts)) flat[policy] = agents.size;
          setBindingCountByPolicy(flat);
        } catch (error) {
          // No permission (or endpoint unavailable) to read bindings directly --
          // "Used by" falls back to Flow references only (see get_references below).
          setBindingCountByPolicy(null);
        }
      }

      // Flow references -- Decision Policy.get_references (whitelisted doc method).
      if (names.length) {
        const entries = await Promise.all(
          names.map(async (name) => {
            try {
              const response = await call.post('frappe.client.run_doc_method', {
                dt: doctype['Decision Policy'],
                dn: name,
                method: 'get_references',
              });
              const refs = (response.message ?? []) as PolicyReference[];
              return [name, Array.isArray(refs) ? refs : []] as const;
            } catch {
              return [name, []] as const;
            }
          })
        );
        setFlowRefsByPolicy(Object.fromEntries(entries));
      }

      // Decision models -- to resolve default_model display name and the
      // "unreachable" badge (no enabled deployment for the policy's model).
      try {
        const models = await listDecisionModels();
        setModelsByName(Object.fromEntries(models.map((m) => [m.name, m])));
      } catch (error) {
        handleFrappeError(error, 'Error loading decision models');
      }
    } catch (error) {
      handleFrappeError(error, 'Error loading decision policies');
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return policies.filter((p) => {
      if (purpose !== 'all' && p.purpose !== purpose) return false;
      const effectiveStatus = versionByPolicy[p.name]?.status || 'Draft';
      if (status !== 'all' && effectiveStatus !== status) return false;
      if (q) {
        const haystack = `${p.policy_name || p.name} ${p.name}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [policies, purpose, status, search, versionByPolicy]);

  const hasFilters = Boolean(search) || purpose !== 'all' || status !== 'all';

  function usedByLabel(name: string): string {
    const flowCount = flowRefsByPolicy[name]?.length || 0;
    const bindingCount = bindingCountByPolicy?.[name] || 0;
    const parts: string[] = [];
    if (bindingCount > 0) parts.push(`${bindingCount} agent${bindingCount === 1 ? '' : 's'}`);
    if (flowCount > 0) parts.push(`${flowCount} flow${flowCount === 1 ? '' : 's'}`);
    if (parts.length === 0) return '—';
    return parts.join(', ');
  }

  function isUnreachable(name?: string): boolean {
    if (!isAdmin || !name) return false;
    const model = modelsByName[name];
    if (!model) return false;
    if (!model.deployments) return false;
    return !model.deployments.some((d) => d.enabled);
  }

  return (
    <PageFrame
      title="Decisions"
      meta={policies.length ? `${policies.length} ${policies.length === 1 ? 'policy' : 'policies'}` : undefined}
      actions={
        canAuthor && (
          <Button size="sm" onClick={() => navigate('/decisions/new')}>
            New policy
          </Button>
        )
      }
      filters={
        <FilterBar
          searchPlaceholder="Search policies..."
          searchValue={search}
          onSearchChange={(value) => {
            setSearch(value);
            updateSearchParams({ q: value });
          }}
          filters={[
            {
              label: 'Purpose',
              value: purpose,
              options: PURPOSE_OPTIONS,
              onChange: (value) => {
                setPurpose(value);
                updateSearchParams({ purpose: value });
              },
            },
            {
              label: 'Status',
              value: status,
              options: STATUS_OPTIONS,
              onChange: (value) => {
                setStatus(value);
                updateSearchParams({ status: value });
              },
            },
          ]}
        />
      }
    >
      <RuntimeDisabledBanner />
      <p className="text-sm font-body text-steel mb-4">
        A Decision Policy asks a model one or more bounded questions (pick one, yes/no, score) and
        routes on the answer. Used by agents, flows, and automations for fast, cheap decisions.
      </p>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
        </div>
      ) : filtered.length === 0 ? (
        hasFilters ? (
          <EmptyState
            variant="no-results"
            icon={GitBranch}
            title="No policies found"
            filterTerm={search}
            secondaryAction={{
              label: 'Clear filters',
              onClick: () => {
                setSearch('');
                setPurpose('all');
                setStatus('all');
                setSearchParams({});
              },
            }}
          />
        ) : (
          <EmptyState
            variant="create"
            icon={GitBranch}
            title="No policies yet"
            description="Create a Decision Policy to give agents, flows, and automations a fast, auditable way to decide."
            action={canAuthor ? { label: 'New policy', onClick: () => navigate('/decisions/new') } : undefined}
          />
        )
      ) : (
        <div className="border border-line bg-panel">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Purpose</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Used by</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((policy) => {
                const version = versionByPolicy[policy.name];
                const effectiveStatus = version?.status || 'Draft';
                const model = policy.default_model ? modelsByName[policy.default_model] : undefined;
                const unreachable = isUnreachable(policy.default_model);
                return (
                  <TableRow
                    key={policy.name}
                    className="cursor-pointer hover:bg-paper-deep"
                    onClick={() => navigate(`/decisions/${encodeURIComponent(policy.name)}`)}
                  >
                    <TableCell className="max-w-md truncate font-medium text-ink">
                      {policy.policy_name || policy.name}
                    </TableCell>
                    <TableCell className="text-sm">{policy.purpose || 'Generic'}</TableCell>
                    <TableCell className="text-sm">
                      <span className="inline-flex items-center gap-1.5">
                        {model?.display_name || policy.default_model || '—'}
                        {unreachable && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="destructive" size="sm">
                                Unreachable
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent>
                              No enabled deployment for this model — runs will fail until one is
                              enabled on the Decision tab.
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm font-mono">
                      {version ? `v${version.version_number}` : '—'}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(effectiveStatus)}>{effectiveStatus}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-steel">
                      {usedByLabel(policy.name)}
                      {bindingCountByPolicy === null && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="ml-1 text-steel-soft cursor-help">(flows only)</span>
                          </TooltipTrigger>
                          <TooltipContent>
                            Agent binding counts aren't visible with your permissions — this shows
                            Flow references only.
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </PageFrame>
  );
}
