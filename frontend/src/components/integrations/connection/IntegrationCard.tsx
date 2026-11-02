import { Bot, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { getServiceIdentity } from '@/data/serviceIdentity';
import { integrationHealth, integrationTitle } from '@/lib/integrations/health';
import type { IntegrationSettingsDoc } from '@/types/integration.types';
import { formatTimeAgo } from '@/utils/time';
import { IntegrationStatusPill } from './IntegrationStatusPill';

interface IntegrationCardProps {
  setting: IntegrationSettingsDoc;
  onOpen: () => void;
  onUseInAgent: () => void;
}

/** One connection as a health card: logo, friendly name, one status, one sentence about it, two actions. */
export function IntegrationCard({ setting, onOpen, onUseInAgent }: IntegrationCardProps) {
  const identity = getServiceIdentity(setting.service);
  const Logo = identity.icon;
  const health = integrationHealth(setting);
  const title = integrationTitle(setting);
  const problem = health.kind === 'attention' || health.kind === 'not_connected';
  const checked = setting.last_test_at ? `Checked ${formatTimeAgo(setting.last_test_at).toLowerCase()}` : '';
  const line = problem || health.kind === 'unchecked' ? health.detail : health.kind === 'connected' ? health.detail : '';

  return (
    <Card
      role="link"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onOpen();
      }}
      className="flex h-full cursor-pointer flex-col gap-3 p-4 transition-colors hover:border-primary/40"
      data-testid={`integration-card-${setting.name}`}
      data-status={health.kind}
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Logo className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <h3 className="line-clamp-2 break-words text-body-text font-semibold leading-snug text-ink" title={title} data-testid="integration-card-title">
            {title}
          </h3>
          <p className="break-words text-sm text-steel">
            {[title === identity.title ? `Edited ${formatTimeAgo(setting.modified).toLowerCase()}` : identity.title, setting.is_default ? 'Default' : '']
              .filter(Boolean)
              .join(' · ')}
          </p>
          <IntegrationStatusPill health={health} />
        </div>
      </div>

      <div className="min-h-[2.75rem] flex-1">
        {line && (
          <p
            className={`line-clamp-2 break-words text-sm ${problem ? 'text-foreground' : 'text-steel'}`}
            title={line}
            data-testid="integration-card-detail"
          >
            {line}
          </p>
        )}
        {checked && <p className="mt-1 text-xs text-steel-soft">{checked}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onUseInAgent();
          }}
          data-testid={`integration-use-in-agent-${setting.name}`}
        >
          <Bot className="mr-1.5 h-4 w-4" />
          Use in agent
        </Button>
        <Button
          type="button"
          variant={problem ? 'default' : 'ghost'}
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
          data-testid={`integration-open-${setting.name}`}
        >
          {problem ? 'Fix this' : (<><Settings className="mr-1.5 h-4 w-4" />Settings</>)}
        </Button>
      </div>
    </Card>
  );
}
