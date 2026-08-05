import { PageFrame } from '@/layouts/PageFrame';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ExternalLink, Terminal, Shield, Cpu } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function SshPage() {
  const navigate = useNavigate();

  return (
    <PageFrame
      title="SSH execution"
      badge={<ExperimentalBadge />}
    >
      <div className="max-w-4xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="w-5 h-5" />
              SSH remote execution
            </CardTitle>
            <CardDescription>
              Execute single remote commands on managed hosts via host-key verification and Redis-backed state locks.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-steel">
            <div className="rounded-lg border border-line bg-paper-deep p-4 space-y-2">
              <h3 className="font-semibold text-ink flex items-center gap-2">
                <Shield className="w-4 h-4 text-steel" />
                Connection allowlisting & credentials
              </h3>
              <p>
                SSH credentials, host-key verification, and connection profiles are configured in Frappe Desk using the <strong>SSH Connection</strong> DocType.
              </p>
            </div>

            <div className="rounded-lg border border-line bg-paper-deep p-4 space-y-2">
              <h3 className="font-semibold text-ink flex items-center gap-2">
                <Cpu className="w-4 h-4 text-steel" />
                Agent configuration
              </h3>
              <p>
                Enable SSH execution for specific agents under their <strong>Advanced Settings</strong> tab. Select allowlisted connections and execution profiles.
              </p>
              <div className="pt-2">
                <Button variant="outline" size="sm" onClick={() => navigate('/agents')} className="gap-2">
                  Configure agents
                  <ExternalLink className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageFrame>
  );
}

export default SshPage;
