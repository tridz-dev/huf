import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  getAgentProcedure,
  getAgentProcedureVersionHistory,
  getSourceFlowId,
  type AgentProcedureDoc,
} from '@/services/agentProcedureApi';
import { formatTimeAgo } from '@/utils/time';

export { AgentProcedureDetailPage };
export default AgentProcedureDetailPage;

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
