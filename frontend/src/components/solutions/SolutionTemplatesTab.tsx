import { useState } from 'react';
import { Link } from 'react-router-dom';
import { TemplatesTab } from '@/components/whatsapp/TemplatesTab';
import type { SolutionOverview } from '@/types/solutions';

const nativeSelect =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function SolutionTemplatesTab({ overview }: { overview: SolutionOverview }) {
  const [picked, setPicked] = useState('');
  const gateways = overview.runs_on;
  const gateway = gateways.find((g) => g.gateway === picked)?.gateway ?? gateways[0]?.gateway;

  return (
    <div className="space-y-3">
      <p className="text-sm text-steel">
        Templates live on the WhatsApp account at Meta. This list shows the ones this solution uses. Manage the full set in{' '}
        <Link
          to={gateway ? `/whatsapp?tab=templates&gateway=${encodeURIComponent(gateway)}` : '/whatsapp?tab=templates'}
          className="font-medium text-ink underline"
        >
          Settings &gt; WhatsApp
        </Link>
        .
      </p>
      {gateways.length > 1 ? (
        <div className="flex items-center gap-2">
          <label htmlFor="tpl-number" className="text-sm text-steel">Number</label>
          <select id="tpl-number" className={nativeSelect} value={gateway} onChange={(e) => setPicked(e.target.value)}>
            {gateways.map((g) => <option key={g.gateway} value={g.gateway}>{g.label}</option>)}
          </select>
        </div>
      ) : null}
      {gateway ? (
        <TemplatesTab key={gateway} gateway={gateway} scopeSolution={overview.name} />
      ) : (
        <p className="text-sm text-steel">This solution does not run on a WhatsApp number yet.</p>
      )}
    </div>
  );
}
