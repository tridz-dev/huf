import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getArtifact, type AgentContextArtifactDoc } from '@/services/agentContextArtifactApi';
import { formatTimeAgo } from '@/utils/time';

export { AgentContextArtifactDetailPage };
export default AgentContextArtifactDetailPage;

function formatJson(raw?: string): string {
  if (!raw) return '';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function AgentContextArtifactDetailPage() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const navigate = useNavigate();
  const [artifact, setArtifact] = useState<AgentContextArtifactDoc | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!artifactId) {
      setLoading(false);
      return;
    }
    (async () => {
      setLoading(true);
      const data = await getArtifact(artifactId);
      setArtifact(data ?? null);
      setLoading(false);
    })();
  }, [artifactId]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-steel">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading artifact...</span>
        </div>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-4xl mx-auto space-y-4">
          <Button variant="ghost" className="px-0" onClick={() => navigate('/artifacts')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <Card>
            <CardHeader>
              <CardTitle>Artifact not found</CardTitle>
              <CardDescription>This context artifact could not be loaded.</CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <Button variant="ghost" className="px-0" onClick={() => navigate('/artifacts')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-3">
                {artifact.name}
                <Badge variant="secondary">{artifact.artifact_type || 'Unknown'}</Badge>
              </CardTitle>
              <CardDescription className="mt-1">
                {artifact.summary || 'No summary recorded.'}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 text-sm">
            <div>
              <div className="text-steel">Conversation</div>
              <div className="font-mono">{artifact.conversation || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Agent Run</div>
              <div className="font-mono">{artifact.agent_run || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Visibility</div>
              <div>{artifact.visibility || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Context Policy</div>
              <div>{artifact.context_policy || '—'}</div>
            </div>
            <div>
              <div className="text-steel">Token Estimate</div>
              <div>{artifact.token_estimate ?? '—'}</div>
            </div>
            <div>
              <div className="text-steel">Created</div>
              <div>{formatTimeAgo(artifact.creation ?? null)}</div>
            </div>
            {artifact.reference_doctype && (
              <div>
                <div className="text-steel">Reference</div>
                <div className="font-mono">
                  {artifact.reference_doctype} / {artifact.reference_name || '—'}
                </div>
              </div>
            )}
            {artifact.expires_on && (
              <div>
                <div className="text-steel">Expires On</div>
                <div>{formatTimeAgo(artifact.expires_on)}</div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Payload</CardTitle>
            <CardDescription>
              {artifact.artifact_type === 'File'
                ? 'Attached file for this artifact.'
                : 'Content stored for this artifact, rendered as read-only text.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {artifact.artifact_type === 'File' ? (
              artifact.payload_file ? (
                <a
                  href={artifact.payload_file}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-primary hover:underline break-all"
                >
                  {artifact.payload_file}
                </a>
              ) : (
                <div className="text-sm font-body text-steel-soft">No file attached.</div>
              )
            ) : (
              <pre className="rounded-none bg-paper-deep p-3 text-sm whitespace-pre-wrap break-words max-h-[420px] overflow-auto">
                {formatJson(artifact.payload_json) || 'No payload recorded.'}
              </pre>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
