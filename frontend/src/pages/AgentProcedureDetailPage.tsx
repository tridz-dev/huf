import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, PlayCircle, ShieldCheck, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { usePermissions } from '@/contexts/PermissionsContext';
import {
  approveProcedure,
  getAgentProcedure,
  getAgentProcedureVersionHistory,
  getSourceFlowId,
  requestProcedureApproval,
  runProcedureValidation,
  type AgentProcedureDoc,
  type ProcedureValidationResult,
} from '@/services/agentProcedureApi';
import { formatTimeAgo } from '@/utils/time';

/** System Manager maps to the "Huf Admin" Huf role server-side (see AgentsPage.tsx /
 * AgentFormPage.tsx for the same convention) -- Huf Admin and Huf Manager are both
 * eligible to approve/reject a write Procedure per
 * huf.ai.procedure_approval_api.APPROVAL_MANAGER_ROLES. */
function canApproveProcedures(hufRole: string | null): boolean {
  return hufRole === 'Huf Admin' || hufRole === 'Huf Manager';
}

export { AgentProcedureDetailPage, ProcedureValidationResultCard };
export default AgentProcedureDetailPage;

/** Standalone display of one `run_validation_harness` result. Kept separate from
 * `AgentProcedureDetailPage` so any other surface (e.g. a future test-run drawer or a
 * standalone "Test" flow) can render the same result without pulling in the whole detail
 * page. */
function ProcedureValidationResultCard({ result }: { result: ProcedureValidationResult }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {result.promotion.approved ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : (
            <XCircle className="w-4 h-4 text-amber-600" />
          )}
          Validation harness result
        </CardTitle>
        <CardDescription>
          {result.promotion.approved ? 'Promotion approved' : 'Not approved for promotion'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {result.promotion.reasons.length > 0 && (
          <div>
            <div className="text-steel mb-1">Reasons</div>
            <ul className="list-disc pl-5 space-y-1">
              {result.promotion.reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <div className="text-steel mb-1">Runs evaluated ({result.runs.length})</div>
          {result.runs.length === 0 ? (
            <div className="text-steel-soft">No terminal runs found for this procedure.</div>
          ) : (
            <div className="space-y-1">
              {result.runs.map((run) => (
                <div key={run.run_name} className="flex items-center gap-2">
                  {run.passed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  )}
                  <span className="font-mono">{run.run_name}</span>
                  <Badge variant="outline">{run.status}</Badge>
                  {run.error && <span className="text-steel-soft truncate">{run.error}</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        {result.diagnostics.length > 0 && (
          <div>
            <div className="text-steel mb-1">Diagnostics</div>
            <ul className="list-disc pl-5 space-y-1 text-steel-soft">
              {result.diagnostics.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatJson(raw?: string): string {
  if (!raw) return '';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

/** Presence of a fingerprint plus a non-empty definition graph is the closest read-only
 * signal available in this doc to "this procedure passed the validation harness" — the
 * validator itself runs server-side (huf.ai.graph.validator) and isn't re-run here. */
function validationStatus(doc: AgentProcedureDoc): { ok: boolean; label: string } {
  const hasDefinition = !!doc.definition_json && doc.definition_json !== '{}';
  const hasFingerprint = !!doc.fingerprint;
  if (hasDefinition && hasFingerprint) {
    return { ok: true, label: 'Fingerprinted — passed validation' };
  }
  if (!hasDefinition) {
    return { ok: false, label: 'No definition graph' };
  }
  return { ok: false, label: 'Not yet fingerprinted' };
}

function AgentProcedureDetailPage() {
  const { procedureId } = useParams<{ procedureId: string }>();
  const navigate = useNavigate();
  const [procedure, setProcedure] = useState<AgentProcedureDoc | null>(null);
  const [versions, setVersions] = useState<AgentProcedureDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState<ProcedureValidationResult | null>(null);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const { hufRole } = usePermissions();

  useEffect(() => {
    if (!procedureId) {
      setLoading(false);
      return;
    }
    (async () => {
      setLoading(true);
      const data = await getAgentProcedure(procedureId);
      setProcedure(data ?? null);
      if (data?.procedure_id) {
        setVersions(await getAgentProcedureVersionHistory(data.procedure_id, data.name));
      } else {
        setVersions([]);
      }
      setLoading(false);
    })();
  }, [procedureId]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-steel">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading procedure...</span>
        </div>
      </div>
    );
  }

  if (!procedure) {
    return (
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-4xl mx-auto space-y-4">
          <Button variant="ghost" className="px-0" onClick={() => navigate('/procedures')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <Card>
            <CardHeader>
              <CardTitle>Procedure not found</CardTitle>
              <CardDescription>This Agent Procedure could not be loaded.</CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    );
  }

  const sourceFlowId = getSourceFlowId(procedure);
  const validation = validationStatus(procedure);

  async function handleRunTest() {
    if (!procedure) return;
    setTestRunning(true);
    try {
      const result = await runProcedureValidation(procedure.name);
      setTestResult(result ?? null);
    } finally {
      setTestRunning(false);
    }
  }

  async function handleRequestReview() {
    if (!procedure) return;
    setApprovalBusy(true);
    try {
      const result = await requestProcedureApproval(procedure.name);
      if (result) setProcedure({ ...procedure, approval_status: result.approval_status });
    } finally {
      setApprovalBusy(false);
    }
  }

  async function handleApprovalDecision(approve: boolean) {
    if (!procedure) return;
    setApprovalBusy(true);
    try {
      const result = await approveProcedure(procedure.name, approve);
      if (result) {
        setProcedure({
          ...procedure,
          approval_status: result.approval_status,
          approved_by: result.approved_by,
          approved_at: result.approved_at,
        });
      }
    } finally {
      setApprovalBusy(false);
    }
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <Button variant="ghost" className="px-0" onClick={() => navigate('/procedures')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-3">
                {procedure.procedure_name || procedure.name}
                <Badge variant="secondary">{procedure.tier || 'Draft'}</Badge>
                <Badge variant="outline">{procedure.status || 'Draft'}</Badge>
              </CardTitle>
              <CardDescription className="mt-1">{procedure.name}</CardDescription>
            </div>
            <Button variant="outline" onClick={handleRunTest} disabled={testRunning}>
              {testRunning ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <PlayCircle className="w-4 h-4 mr-2" />
              )}
              Test
            </Button>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 text-sm">
            <div>
              <div className="text-steel">Procedure ID</div>
              <div className="font-mono">{procedure.procedure_id || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Version</div>
              <div>{procedure.version ?? '—'}</div>
            </div>
            <div>
              <div className="text-steel">Fingerprint</div>
              <div className="font-mono truncate">{procedure.fingerprint || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Schema Version</div>
              <div>{procedure.schema_version || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Read-only</div>
              <div>{procedure.is_read_only ? 'Yes' : 'No'}</div>
            </div>
            <div>
              <div className="text-steel">Contains Writes</div>
              <div>{procedure.contains_writes ? 'Yes' : 'No'}</div>
            </div>
            <div>
              <div className="text-steel">Contains Code</div>
              <div>{procedure.contains_code ? 'Yes' : 'No'}</div>
            </div>
            {sourceFlowId && (
              <div>
                <div className="text-steel">Source Flow</div>
                <div
                  className="font-mono text-primary hover:underline cursor-pointer"
                  onClick={() => navigate(`/flows/${sourceFlowId}`)}
                >
                  {sourceFlowId}
                </div>
              </div>
            )}
            <div>
              <div className="text-steel">Updated</div>
              <div>{formatTimeAgo(procedure.updated_at ?? procedure.modified ?? null)}</div>
            </div>
          </CardContent>
        </Card>

        {!procedure.is_read_only && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4" />
                Approval
              </CardTitle>
              <CardDescription>
                This is a write Procedure (I8). It cannot be bound to an agent until a System
                Manager or Huf Manager approves it here.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center gap-3">
                <span className="text-steel">Status</span>
                <Badge
                  variant={
                    procedure.approval_status === 'Approved'
                      ? 'success'
                      : procedure.approval_status === 'Rejected'
                        ? 'destructive'
                        : 'outline'
                  }
                >
                  {procedure.approval_status || 'Not Requested'}
                </Badge>
              </div>

              {(procedure.approved_by || procedure.approved_at) && (
                <div className="text-steel-soft text-xs">
                  {procedure.approval_status === 'Approved' ? 'Approved' : 'Reviewed'} by{' '}
                  {procedure.approved_by || '—'}
                  {procedure.approved_at ? ` (${formatTimeAgo(procedure.approved_at)})` : ''}
                </div>
              )}

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRequestReview}
                  disabled={approvalBusy || procedure.approval_status === 'Approved'}
                >
                  {approvalBusy ? <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> : null}
                  Request Review
                </Button>

                {canApproveProcedures(hufRole) && (
                  <>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => handleApprovalDecision(true)}
                      disabled={approvalBusy || procedure.approval_status === 'Approved'}
                    >
                      Approve
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleApprovalDecision(false)}
                      disabled={approvalBusy}
                    >
                      Reject
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {validation.ok ? (
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              ) : (
                <XCircle className="w-4 h-4 text-amber-600" />
              )}
              Validation status
            </CardTitle>
            <CardDescription>{validation.label}</CardDescription>
          </CardHeader>
        </Card>

        {testResult && <ProcedureValidationResultCard result={testResult} />}

        <Card>
          <CardHeader>
            <CardTitle>Definition</CardTitle>
            <CardDescription>The compiled procedure graph, rendered read-only.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="rounded-none bg-paper-deep p-3 text-sm whitespace-pre-wrap break-words max-h-[480px] overflow-auto">
              {formatJson(procedure.definition_json) || 'No definition recorded.'}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Version history</CardTitle>
            <CardDescription>Other versions sharing this procedure_id.</CardDescription>
          </CardHeader>
          <CardContent>
            {versions.length === 0 ? (
              <div className="text-sm font-body text-steel-soft">No other versions recorded.</div>
            ) : (
              <div className="space-y-2">
                {versions.map((v) => (
                  <div
                    key={v.name}
                    className="flex items-center justify-between gap-4 border border-line px-3 py-2 cursor-pointer hover:bg-paper-deep"
                    onClick={() => navigate(`/procedures/${v.name}`)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm">v{v.version ?? '—'}</span>
                      <Badge variant="outline">{v.status || 'Draft'}</Badge>
                    </div>
                    <span className="text-xs text-steel">{formatTimeAgo(v.modified ?? null)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
